import os
import time
import requests
from flask import Flask, session, render_template, request, flash, redirect, url_for, abort, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from helpers import login_required

from pdkdf2 import hash_password, verify_password


app = Flask(__name__)
#for sessions. generates a random 24 chracter string
app.secret_key = os.urandom(24)
# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

#Register
@app.route("/register", methods=["POST","GET"])
def register():

    session.clear()
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")
        cpassword = request.form.get("cpassword")
        #check if username exists
        usercheck = db.execute("SELECT * FROM users where username = :username",{"username": username}).fetchone()

        if not password == cpassword:
            flash('Error: passwords do not match')
            return render_template("register.html")
        elif usercheck:
            flash('Error: username already exists')
            return render_template("register.html")

        #convert password to its hash form
        hash = hash_password(password)

        db.execute("INSERT INTO users (username, password) VALUES(:username, :password)",
                    {"username": username, "password": hash})
        db.commit()
        flash('Account created!')
        return redirect("/login") #render_template

    else:
        return render_template("register.html")

#Login
@app.route("/login", methods=["POST","GET"])
def login():

    session.clear()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        usercheck = db.execute("SELECT * from users where username= :username",
                                {"username": username}).fetchone()
        if usercheck == None or not verify_password(usercheck[2], password):
            flash('username or password is incorrect')
            return render_template("login.html")

        session["userid"] = usercheck[0]
        session["username"] = usercheck[1]
        return redirect('/')

    #user reaches route via get request.
    else:
        return render_template("login.html")

#logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

#Search for books
@app.route("/", methods=["GET","POST"])
@login_required
def index():
    if request.method == "POST":
        query = request.form.get("searchbar")
        if query:
            query = ''.join(('%',query,'%')).upper()
            print(query, flush=True)
        #get all books wich satisfy the query

        books = db.execute("SELECT * FROM books where isbn LIKE :query or UPPER(title) like :query or UPPER(author) like :query limit 20",{"query": query}).fetchall()
        if len(books) == 0:
            flash('no books matching that description found')
            return render_template("index.html")
        if request.form.get('goback') == 'goback':
            return render_template("index.html", query=query)

        return render_template("result.html",books=books)

        #return render_template("index.html")

    return render_template("index.html")

#display book page and save user reviews
@app.route("/book/<isbn>", methods=["GET","POST"])
@login_required
def book(isbn):

    # gives me id
    bookinfo = db.execute("SELECT id FROM books where isbn= :isbn",{"isbn":isbn}).fetchone()
    #display available Reviews
    display = db.execute("select reviews.userid, reviews.id, reviews.rating, reviews.comments, users.username from reviews full join users on reviews.userid = users.userid where reviews.id= :id "
                        ,{"id": bookinfo['id']}).fetchall()
    print(display,flush=True)
    #info about current user
    userid = session["userid"]

    # Post request implies form is submitted, so insert details into reviews table.
    if request.method == "POST":
        rating = request.form.get('rating')
        comments = request.form.get('comments')
        isbn = str(isbn)

        #check if review already gven
        rcheck = db.execute("Select * from reviews where userid= :userid and id= :id",{"userid":userid, "id":bookinfo['id']}).fetchall()
        print(rcheck,flush=True)
        if rcheck:
            flash('Warning! You have already submitted a review for this book')
            return redirect("/book/"+ isbn)
        else:
            db.execute("INSERT INTO reviews(userid,id,rating,comments) VALUES(:userid,:id,:rating,:comments)",
                        {"userid": session['userid'], "id": bookinfo['id'], "rating": rating, "comments": comments})
            db.commit()
            flash('YAYY Review submitted! ')
            return redirect("/book/"+ isbn, code=307)#https://stackoverflow.com/questions/26905306/how-to-redirect-to-an-external-url-with-parameters-and-post-method

    else:
        bookinfo = db.execute("SELECT * FROM books where isbn= :isbn",{"isbn":isbn}).fetchone() #gives me title, author, isbn and year
        goodreads = requests.get("https://www.goodreads.com/book/review_counts.json", params={'key':'AB7cZ0QR0yRxuMWACtDGbw', 'isbns': isbn})
        average_rating = goodreads.json()["books"][0]["average_rating"]
        review_count = goodreads.json()["books"][0]["work_reviews_count"]
        reviews = db.execute("SELECT * FROM reviews where id = :id",{"id": bookinfo['id']}).fetchall()

        return render_template("book.html", bookinfo = bookinfo, reviews = reviews, average_rating= average_rating, review_count= review_count,
                                display=display)

@app.route("/api/<isbn>", methods=['GET'])
def api(isbn):
    query_book = db.execute("SELECT * from books where isbn = :isbn",{"isbn":isbn}).fetchone()
    if query_book:
        #collect info from website's api
        goodreads = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key":"AB7cZ0QR0yRxuMWACtDGbw", "isbns": isbn})
        #print(goodreads, flush=True)
        average_rating = goodreads.json()["books"][0]["average_rating"]
        review_count = goodreads.json()["books"][0]["work_reviews_count"]

        #arrange all info in a dictionary
        response = {'title': query_book['title'], 'author': query_book['author'], 'isbn':query_book['isbn'], 'year': query_book['year'],
                    'average_rating': average_rating, 'review_count':review_count}
        return jsonify(response)
    # if no book found, display 404 Error
    else:
        response = "Error 404: Not found "
        return jsonify(response)
