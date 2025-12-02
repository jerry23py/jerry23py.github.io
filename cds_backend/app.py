from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import time
import sqlite3
import requests

app = Flask(__name__)
CORS(app)  # allows frontend to call API

# Database setup
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///donations.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# Database Model
class Donation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(150), nullable=False)
    statecode = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    reference = db.Column(db.String(50), unique=True, nullable=False)
    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# Initialize DB
with app.app_context():
    db.create_all()

# Paystack configuration

PAYSTACK_SECRET_KEY = "YOUR_SECRET_KEY_HERE"

# -------- DATABASE SETUP ----------
def create_table():
    conn = sqlite3.connect("donations.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS donations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fullname TEXT,
            statecode TEXT,
            phone TEXT,
            amount INTEGER,
            reference TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()
    conn.close()

create_table()


# ---------- DONATION ROUTE -----------
@app.route("/donate", methods=["POST"])
def donate():
    data = request.get_json()

    fullname = data["fullname"]
    statecode = data["statecode"]
    phone = data["phone"]
    amount = int(data["amount"]) * 100  # Paystack uses kobo

    # create Paystack transaction
    url = "https://api.paystack.co/transaction/initialize"

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "email": f"{statecode}@donor.com",  # Paystack requires email
        "amount": amount
    }

    response = requests.post(url, json=payload, headers=headers).json()

    if not response["status"]:
        return jsonify({"message": "Paystack error"}), 400

    reference = response["data"]["reference"]
    payment_url = response["data"]["authorization_url"]

    # save donor temporarily in DB
    conn = sqlite3.connect("donations.db")
    c = conn.cursor()
    c.execute("INSERT INTO donations (fullname, statecode, phone, amount, reference) VALUES (?, ?, ?, ?, ?)",
              (fullname, statecode, phone, amount, reference))
    conn.commit()
    conn.close()

    return jsonify({"payment_url": payment_url})



# Route to check status
@app.route("/donation-status/<reference>", methods=["GET"])
def donation_status(reference):
    donation = Donation.query.filter_by(reference=reference).first()

    if not donation:
        return jsonify({"message": "Reference not found"}), 404

    return jsonify({
        "fullname": donation.fullname,
        "statecode": donation.statecode,
        "amount": donation.amount,
        "status": donation.status,
        "reference": donation.reference
    })
@app.route("/paystack/webhook", methods=["POST"])
def paystack_webhook():
    event = request.get_json()

    if event["event"] == "charge.success":
        reference = event["data"]["reference"]

        conn = sqlite3.connect("donations.db")
        c = conn.cursor()
        c.execute("UPDATE donations SET status='paid' WHERE reference=?", (reference,))
        conn.commit()
        conn.close()

    return jsonify({"status": "success"}), 200



if __name__ == "__main__":
    app.run(debug=True)
