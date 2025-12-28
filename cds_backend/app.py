from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import time
import sqlite3
import uuid
import os
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from flask import send_from_directory, abort, request as flask_request

# token support (URLSafeTimedSerializer works across itsdangerous versions)
from itsdangerous import URLSafeTimedSerializer as Serializer, BadSignature, SignatureExpired

# Load local .env if present (for local development). The file is gitignored.
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

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
    proof_filename = db.Column(db.String(255), nullable=True)
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

# Admin configuration for donation validation

# Load sensitive config from environment variables
# ADMIN_SECRET is used as the admin password; set this to a secure value in production
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "admin123")
if not os.environ.get("ADMIN_SECRET"):
    app.logger.warning("ADMIN_SECRET not set. Using default insecure admin key; set ADMIN_SECRET in env for production.")
# Secret key used to sign admin tokens
SECRET_KEY = os.environ.get("SECRET_KEY") or os.environ.get("FLASK_SECRET") or (os.urandom(24).hex())
# token expiry in seconds
ADMIN_TOKEN_EXPIRY = int(os.environ.get("ADMIN_TOKEN_EXPIRY", 3600))
DB_PATH = os.environ.get("DONATIONS_DB", "donations.db")
UPLOAD_FOLDER = os.environ.get("GALLERY_FOLDER", os.path.join(os.getcwd(), "gallery_images"))
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf"}

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# serializer for admin tokens
_token_serializer = Serializer(SECRET_KEY, salt='admin-token')

def generate_admin_token():
    # URLSafeTimedSerializer.dumps returns a string
    return _token_serializer.dumps({"role": "admin"})


def verify_admin_token(token):
    try:
        _token_serializer.loads(token, max_age=ADMIN_TOKEN_EXPIRY)
        return True
    except SignatureExpired:
        return False
    except BadSignature:
        return False


def is_admin_authorized(req):
    # Accept Authorization: Bearer <token> or legacy X-ADMIN-KEY (admin password) for compatibility
    auth = req.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        token = auth.split(' ', 1)[1].strip()
        return verify_admin_token(token)
    legacy = req.headers.get('X-ADMIN-KEY', '')
    if legacy and legacy == ADMIN_SECRET:
        return True
    # allow token via query param for anchor links
    t = req.args.get('token')
    if t:
        return verify_admin_token(t)
    return False
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# -------- DATABASE SETUP ----------
# Ensure donations table has a column for proof_filename (filename of uploaded receipt)
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
            status TEXT DEFAULT 'pending',
            proof_filename TEXT
        )
    """)
    # If the column didn't exist in older DBs, add it
    c.execute("PRAGMA table_info(donations)")
    cols = [r[1] for r in c.fetchall()]
    if 'proof_filename' not in cols:
        c.execute("ALTER TABLE donations ADD COLUMN proof_filename TEXT")

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
    # Accept multipart form with a required proof of payment file (field name: 'proof')
    fullname = flask_request.form.get("fullname", "").strip()
    email = flask_request.form.get("email", "").strip()
    phone = flask_request.form.get("phone", "").strip()

    try:
        amount = int(float(flask_request.form.get("amount", 0)))
    except Exception:
        return jsonify({"message": "Invalid amount provided"}), 400

    # Validate input
    if not fullname or not email or not amount:
        return jsonify({"message": "Full name, email, and amount are required"}), 400

    proof = flask_request.files.get('proof')
    if not proof or proof.filename == '':
        return jsonify({"message": "Proof of payment file is required"}), 400
    if not allowed_file(proof.filename):
        return jsonify({"message": "Unsupported proof file type (allowed: png,jpg,jpeg,gif,pdf)"}), 400

    filename = secure_filename(proof.filename)
    prefix = str(int(time.time()))
    stored_name = f"{prefix}_{filename}"
    save_path = os.path.join(UPLOAD_FOLDER, stored_name)
    try:
        proof.save(save_path)
    except Exception as e:
        app.logger.error(f"Failed to save proof file: {e}")
        return jsonify({"message": "Failed to save proof file"}), 500

    # generate a unique reference
    reference = uuid.uuid4().hex[:12]

    # save donor as pending with proof filename in DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO donations (fullname, phone, amount, reference, proof_filename, status) VALUES (?, ?, ?, ?, ?, 'pending')",
              (fullname, phone, amount, reference, stored_name))
    conn.commit()
    conn.close()

    message = (
        "Donation recorded as pending with proof of payment.\n"
        "An admin will review your proof and validate the donation once confirmed.\n"
        "Please keep the reference for follow-up."
    )

    return jsonify({"reference": reference, "message": message}), 201



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
@app.route("/pending-donations", methods=["GET"])
def pending_donations():
    # Admin endpoint - requires valid admin token
    if not is_admin_authorized(request):
        return jsonify({"message": "Unauthorized"}), 401

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT fullname, phone, amount, reference, status, proof_filename FROM donations WHERE status='pending'")
    rows = c.fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({'fullname': r[0], 'phone': r[1], 'amount': r[2], 'reference': r[3], 'status': r[4], 'proof_filename': r[5]})
    return jsonify(result)


@app.route('/paid-users', methods=['GET'])
def paid_users():
    # protect this endpoint
    if not is_admin_authorized(request):
        return jsonify({"message": "Unauthorized"}), 401
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT fullname, phone, amount, reference, status, proof_filename FROM donations WHERE status='paid'")
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({'fullname': r[0], 'phone': r[1], 'amount': r[2], 'reference': r[3], 'status': r[4], 'proof_filename': r[5]})
    return jsonify(result)

@app.route("/admin/validate-donation", methods=["POST"])
def validate_donation():
    # Admin endpoint - marks a donation as paid
    if not is_admin_authorized(request):
        return jsonify({"message": "Unauthorized"}), 401

    data = request.get_json() or {}
    reference = data.get("reference")
    if not reference:
        return jsonify({"message": "Reference required"}), 400

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # only update if not already paid
    c.execute("UPDATE donations SET status='paid' WHERE reference=? AND status!='paid'", (reference,))
    if c.rowcount == 0:
        # check if the reference exists and is already paid
        c2 = conn.cursor()
        c2.execute("SELECT status FROM donations WHERE reference=?", (reference,))
        row = c2.fetchone()
        conn.close()
        if row and row[0] == 'paid':
            return jsonify({"message": "Already marked as paid"}), 200
        return jsonify({"message": "Reference not found"}), 404
    conn.commit()
    conn.close()

    return jsonify({"message": "Donation validated"}), 200


@app.route('/admin/reset-donations', methods=['POST'])
def admin_reset_donations():
    if not is_admin_authorized(request):
        return jsonify({"message": "Unauthorized"}), 401

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT proof_filename FROM donations WHERE proof_filename IS NOT NULL")
    rows = c.fetchall()
    # delete files if exist
    deleted_files = 0
    for r in rows:
        fname = r[0]
        if not fname:
            continue
        path = os.path.join(UPLOAD_FOLDER, fname)
        try:
            if os.path.exists(path):
                os.remove(path)
                deleted_files += 1
        except Exception as e:
            app.logger.warning(f"Failed to delete proof file {path}: {e}")

    c.execute("DELETE FROM donations")
    deleted = c.rowcount
    conn.commit()
    conn.close()

    return jsonify({"message": "Donations reset", "deleted_files": deleted_files, "deleted_rows": deleted}), 200


# ---------------- GALLERY / IMAGES ----------------
@app.route('/upload-image', methods=['POST'])
def upload_image():
    # Support multiple files (album upload). Accepts form fields:
    # - file: one or more files (multipart)
    # - album_title: optional title applied to all files
    # - album_date: optional date (taken_at) applied to all files
    files = flask_request.files.getlist('file')
    if not files or len(files) == 0:
        return jsonify({'message': 'No file part in request'}), 400

    album_title = flask_request.form.get('album_title', '')
    album_date = flask_request.form.get('album_date', None)

    uploaded_urls = []

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    for f in files:
        if not f or f.filename == '':
            continue
        if not allowed_file(f.filename):
            # skip unsupported file types
            app.logger.warning(f"Skipped unsupported file type: {f.filename}")
            continue

        filename = secure_filename(f.filename)
        prefix = str(int(time.time()))
        # include a short random suffix to reduce collision chance when uploading multiple quickly
        stored_name = f"{prefix}_{filename}"
        save_path = os.path.join(UPLOAD_FOLDER, stored_name)
        f.save(save_path)

        # store record in DB using album metadata
        c.execute('INSERT INTO images (filename, title, taken_at, uploaded_at) VALUES (?, ?, ?, ?)',
                  (stored_name, album_title, album_date, datetime.utcnow().isoformat()))

        base = flask_request.host_url.rstrip('/')
        url = f"{base}/gallery-image/{stored_name}"
        uploaded_urls.append(url)

    conn.commit()
    conn.close()

    if len(uploaded_urls) == 0:
        return jsonify({'message': 'No valid images were uploaded'}), 400

    # If only one file was uploaded, keep backward-compatible 'url' field
    if len(uploaded_urls) == 1:
        return jsonify({'message': 'Uploaded', 'url': uploaded_urls[0], 'urls': uploaded_urls}), 201
    return jsonify({'message': 'Uploaded', 'urls': uploaded_urls}), 201


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
    # Public gallery images (unchanged)
    safe = secure_filename(filename)
    full = os.path.join(UPLOAD_FOLDER, safe)
    if not os.path.exists(full):
        abort(404)
    return send_from_directory(UPLOAD_FOLDER, safe)


@app.route('/protected-proof/<path:filename>', methods=['GET'])
def protected_proof(filename):
    # Require admin token (allow ?token=... for browser access)
    if not is_admin_authorized(request):
        return jsonify({"message": "Unauthorized"}), 401
    safe = secure_filename(filename)
    full = os.path.join(UPLOAD_FOLDER, safe)
    if not os.path.exists(full):
        abort(404)
    return send_from_directory(UPLOAD_FOLDER, safe)


# ---------------- ADMIN / EXPORT (paid users) ----------------
# Note: `paid_users` endpoint is defined above including `proof_filename` in the response.

@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json() or {}
    password = data.get('password', '')
    if password != ADMIN_SECRET:
        return jsonify({'message': 'Unauthorized'}), 401
    token = generate_admin_token()
    return jsonify({'token': token, 'expires_in': ADMIN_TOKEN_EXPIRY}), 200


@app.route('/download-csv', methods=['GET'])
def download_csv():
    # protect download with admin token
    if not is_admin_authorized(request):
        return jsonify({"message": "Unauthorized"}), 401
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
    # Serve frontend index when visiting the backend root
    FRONTEND_DIR = os.path.abspath(os.path.join(basedir, '..'))
    index_path = os.path.join(FRONTEND_DIR, 'index.html')
    if os.path.exists(index_path):
        return send_from_directory(FRONTEND_DIR, 'index.html')
    return jsonify({"message": "Backend is running successfully!"})


# Catch-all to serve frontend static files (placed after API routes so APIs take precedence)
@app.route('/<path:path>')
def serve_frontend(path):
    FRONTEND_DIR = os.path.abspath(os.path.join(basedir, '..'))
    # First try files in project root
    candidate = os.path.join(FRONTEND_DIR, path)
    if os.path.exists(candidate):
        return send_from_directory(FRONTEND_DIR, path)
    # Then try files in frontend_cds folder
    candidate = os.path.join(FRONTEND_DIR, 'frontend_cds', path)
    if os.path.exists(candidate):
        return send_from_directory(os.path.join(FRONTEND_DIR, 'frontend_cds'), path)
    # Then try image folder
    candidate = os.path.join(FRONTEND_DIR, 'image', path)
    if os.path.exists(candidate):
        return send_from_directory(os.path.join(FRONTEND_DIR, 'image'), path)
    # Not found — return 404
    abort(404)


if __name__ == "__main__":
    # Use PORT env var if provided (useful for hosting platforms)
    port = int(os.environ.get("PORT", 5000))
    # Bind to 0.0.0.0 so the service is reachable from outside
    app.run(host="0.0.0.0", port=port, debug=(os.environ.get("FLASK_DEBUG", "False") == "True"))
