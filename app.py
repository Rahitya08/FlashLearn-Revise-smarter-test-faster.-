from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
import os

# -------------------------------------------------
# Flask Configuration
# -------------------------------------------------
app = Flask(__name__)

# IMPORTANT: encode special characters in your DB password
# Example password: W7301@jqir#
# Encode: @ -> %40, # -> %23
# So: W7301@jqir#  becomes  W7301%40jqir%23
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://root:W7301%40jqir%23@localhost:3306/flashcard"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.urandom(24)

csrf = CSRFProtect(app)
db = SQLAlchemy(app)

# -------------------------------------------------
# Database Models
# -------------------------------------------------
class Card(db.Model):
    __tablename__ = "cards"
    card_id = db.Column(db.Integer, primary_key=True)
    ques = db.Column(db.Text, nullable=False)
    ans = db.Column(db.Text, nullable=False)
    did = db.Column(db.Integer, db.ForeignKey("decks.deck_id"), nullable=False)

class Deck(db.Model):
    __tablename__ = "decks"
    deck_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    uid = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    cards = db.relationship("Card", backref="deck", lazy=True, cascade="all, delete")
    user = db.relationship("User", back_populates="decks")

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    email = db.Column(db.String(100), nullable=False, unique=True)
    hash = db.Column(db.String(255), nullable=False)
    decks = db.relationship("Deck", back_populates="user", lazy=True, cascade="all, delete")

# -------------------------------------------------
# Routes
# -------------------------------------------------
@app.route('/')
def index():
    if "user" not in session:
        return render_template("index.html")

    user = User.query.filter_by(username=session["user"]).first()
    if not user:
        flash("Error logging In! User not found", "danger")
        session.clear()
        return redirect("/login")

    return render_template("index.html", user=session["user"], decks=user.decks)

@app.route('/add_deck', methods=["GET", "POST"])
def add_deck():
    username = session.get("user")
    if not username:
        flash("You must be logged in to create a deck", "info")
        return redirect("/login")

    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description") or ""

        try:
            num_of_cards = int(request.form.get("num_of_cards"))
        except (TypeError, ValueError):
            flash("Number of Cards must be an Integer!", "danger")
            return redirect("/add_deck")

        if not name:
            flash("Name is Required.", "info")
            return redirect("/add_deck")
        elif len(description) > 255:
            flash("Description must be less than 255 characters!", "info")
            return redirect("/add_deck")
        elif num_of_cards < 1 or num_of_cards > 10:
            flash("Range: 1-10", "warning")
            return redirect("/add_deck")

        user = User.query.filter_by(username=username).first()
        if not user:
            flash("User not found", "danger")
            return redirect("/")

        # Step 1: create deck and commit to get deck_id
        new_deck = Deck(name=name, description=description, user=user)
        db.session.add(new_deck)
        db.session.commit()  # now new_deck.deck_id is set

        # Step 2: add cards with did=new_deck.deck_id
        for i in range(1, num_of_cards + 1):
            ques = request.form.get(f"question{i}")
            ans = request.form.get(f"answer{i}")
            if not ques or not ans:
                continue
            new_card = Card(ques=ques, ans=ans, did=new_deck.deck_id)
            db.session.add(new_card)

        # Step 3: commit cards
        db.session.commit()
        flash("Deck and cards added successfully!", "success")
        return redirect("/")
    else:
        return render_template("add_deck.html")


@app.route('/delete_deck', methods=["POST"])
def delete_deck():
    try:
        did = int(request.form.get("deck_id"))
    except (TypeError, ValueError):
        flash("Invalid deck id!", "warning")
        return redirect("/")

    deck = Deck.query.get(did)
    if deck:
        db.session.delete(deck)
        db.session.commit()
        flash("Deck deleted Successfully!", "success")
    else:
        flash("Deck not found!", "warning")

    return redirect("/")

@app.route('/load_cards')
def load_cards():
    try:
        deck_id = int(request.args.get("deck_id"))
    except (TypeError, ValueError):
        flash("Invalid Deck Id!", "danger")
        return redirect("/")

    cards = Card.query.filter_by(did=deck_id).all()
    cards_dict = [{"card_id": c.card_id, "ques": c.ques, "ans": c.ans, "did": c.did} for c in cards]
    return jsonify(cards_dict)

@app.route('/login', methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("username")
        password = request.form.get("password")

        if not name or not password:
            flash("Username and Password is Required!", "warning")
            return redirect("/login")

        user = User.query.filter_by(username=name).first()
        if not user:
            flash("Username Not Found. <a href='/register'>Register here</a>", "warning")
            return redirect("/login")

        if not check_password_hash(user.hash, password):
            flash("Invalid Password.", "warning")
            return redirect("/login")

        session["user"] = name
        flash("Logged in Successfully!", "success")
        return redirect("/")
    else:
        return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect("/")

@app.route('/register', methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("cnf_pass")

        existing_user = User.query.filter(or_(User.username == name, User.email == email)).first()
        if existing_user:
            flash("Username or email already exists", "info")
            return redirect("/register")

        if password != confirm_password:
            flash("Passwords do not match", "warning")
            return redirect("/register")

        hashed_password = generate_password_hash(password)
        new_user = User(username=name, email=email, hash=hashed_password)

        try:
            db.session.add(new_user)
            db.session.commit()
            flash("Registration Successful!", "success")
            return redirect("/login")
        except IntegrityError:
            db.session.rollback()
            flash("Something went wrong. Try again.", "danger")
            return redirect("/register")
    else:
        return render_template("register.html")

@app.route('/study')
def study():
    deck_id = request.args.get("deck_id")
    if not deck_id:
        flash("Error accessing deck", "warning")
        return redirect("/")

    deck = Deck.query.get(deck_id)
    if not deck:
        flash("Deck not found!", "warning")
        return redirect("/")

    # Convert Card objects to dictionaries so they are JSON serializable
    cards_dict = [{"card_id": c.card_id, "ques": c.ques, "ans": c.ans} for c in deck.cards]

    return render_template(
        "study.html",
        deck_name=deck.name,
        deck_id=deck.deck_id,
        cards=cards_dict
    )



# -------------------------------------------------
# Run + Create Tables
# -------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # ensures tables are created
    app.run(debug=True)
