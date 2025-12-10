from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import time
import sqlite3
import requests
import os
from werkzeug.utils import secure_filename
from flask import send_from_directory, abort, request as flask_request

app = Flask(__name__)
CORS(app)  # allows frontend to call API

# Database setup
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.environ.get('DONATIONS_DB', 'donations.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# Database Model
class Donation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    reference = db.Column(db.String(50), unique=True, nullable=False)
    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# Image model for gallery
class Image(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(255), nullable=True)
    taken_at = db.Column(db.DateTime, nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


# Initialize DB
with app.app_context():
    db.create_all()

# Paystack configuration

# Load sensitive config from environment variables
PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "YOUR_SECRET_KEY_HERE")
DB_PATH = os.environ.get("DONATIONS_DB", "donations.db")
UPLOAD_FOLDER = os.environ.get("GALLERY_FOLDER", os.path.join(os.getcwd(), "gallery_images"))
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# -------- DATABASE SETUP ----------
def create_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS donations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fullname TEXT,
            phone TEXT,
            amount INTEGER,
            reference TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            title TEXT,
            taken_at TEXT,
            uploaded_at TEXT
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
    phone = data["phone"]
    amount = int(data["amount"]) * 100  # Paystack uses kobo

    # create Paystack transaction
    url = "https://api.paystack.co/transaction/initialize"

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "email": f"{fullname}@donor.com",  # Paystack requires email
        "amount": amount
    }

    response = requests.post(url, json=payload, headers=headers).json()

    if not response["status"]:
        return jsonify({"message": "Paystack error"}), 400

    reference = response["data"]["reference"]
    payment_url = response["data"]["authorization_url"]

    # save donor temporarily in DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO donations (fullname, phone, amount, reference) VALUES (?, ?, ?, ?)",
              (fullname, phone, amount, reference))
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
        "amount": donation.amount,
        "status": donation.status,
        "reference": donation.reference
    })
@app.route("/paystack/webhook", methods=["POST"])
def paystack_webhook():
    event = request.get_json()

    if event["event"] == "charge.success":
        reference = event["data"]["reference"]

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE donations SET status='paid' WHERE reference=?", (reference,))
        conn.commit()
        conn.close()

    return jsonify({"status": "success"}), 200


# ---------------- GALLERY / IMAGES ----------------
@app.route('/upload-image', methods=['POST'])
def upload_image():
    # Expect multipart/form-data with fields: file, title, taken_at (ISO date optional)
    if 'file' not in flask_request.files:
        return jsonify({'message': 'No file part in request'}), 400
    file = flask_request.files['file']
    title = flask_request.form.get('title', '')
    taken_at = flask_request.form.get('taken_at', None)

    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # prefix with timestamp to avoid collisions
        prefix = str(int(time.time()))
        stored_name = f"{prefix}_{filename}"
        save_path = os.path.join(UPLOAD_FOLDER, stored_name)
        file.save(save_path)

        # store record in DB
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('INSERT INTO images (filename, title, taken_at, uploaded_at) VALUES (?, ?, ?, ?)',
                  (stored_name, title, taken_at, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()

        # return image URL path
        base = flask_request.host_url.rstrip('/')
        url = f"{base}/gallery-image/{stored_name}"
        return jsonify({'message': 'Uploaded', 'url': url}), 201
    else:
        return jsonify({'message': 'File type not allowed'}), 400


@app.route('/gallery', methods=['GET'])
def gallery_list():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # order by taken_at desc (if set) then title
    c.execute("SELECT id, filename, title, taken_at, uploaded_at FROM images ORDER BY taken_at DESC, title ASC")
    rows = c.fetchall()
    conn.close()

    images = []
    base = flask_request.host_url.rstrip('/')
    for r in rows:
        img = {
            'id': r[0],
            'filename': r[1],
            'title': r[2],
            'taken_at': r[3],
            'uploaded_at': r[4],
            'url': f"{base}/gallery-image/{r[1]}"
        }
        images.append(img)
    return jsonify(images)


@app.route('/gallery-image/<path:filename>', methods=['GET'])
def serve_gallery_image(filename):
    # Prevent path traversal
    safe = secure_filename(filename)
    full = os.path.join(UPLOAD_FOLDER, safe)
    if not os.path.exists(full):
        abort(404)
    return send_from_directory(UPLOAD_FOLDER, safe)


# ---------------- ADMIN / EXPORT (paid users) ----------------
@app.route('/paid-users', methods=['GET'])
def paid_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT fullname, phone, amount, reference, status FROM donations WHERE status='paid'")
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({'fullname': r[0], 'phone': r[1], 'amount': r[2], 'reference': r[3], 'status': r[4]})
    return jsonify(result)


@app.route('/download-csv', methods=['GET'])
def download_csv():
    import csv
    from io import StringIO
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT fullname, phone, amount, reference, status FROM donations")
    rows = c.fetchall()
    conn.close()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['fullname', 'phone', 'amount', 'reference', 'status'])
    for r in rows:
        cw.writerow(r)
    output = si.getvalue()
    return app.response_class(output, mimetype='text/csv', headers={
        'Content-Disposition': 'attachment; filename=donations.csv'
    })

@app.route("/")
def home():
    return jsonify({"message": "Backend is running successfully!"})


if __name__ == "__main__":
    # Use PORT env var if provided (useful for hosting platforms)
    port = int(os.environ.get("PORT", 5000))
    # Bind to 0.0.0.0 so the service is reachable from outside
    app.run(host="0.0.0.0", port=port, debug=(os.environ.get("FLASK_DEBUG", "False") == "True"))
