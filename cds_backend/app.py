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
# Allow CORS for admin routes and public endpoints. Ensure Authorization header is allowed for preflight.
CORS(app, resources={r"/admin/*": {"origins": "*"}, r"/bank-accounts": {"origins": "*"}, r"/bank-accounts/": {"origins": "*"}}, expose_headers=['Content-Type'], supports_credentials=True)  # allows frontend to call API and include Authorization header

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
    approved_by = db.Column(db.String(100), nullable=True)
    approved_at = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# Image model for gallery
class Image(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(255), nullable=True)
    taken_at = db.Column(db.DateTime, nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


# Bank account model for transfer details (managed by admins)
class BankAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bank_name = db.Column(db.String(128), nullable=False)
    account_name = db.Column(db.String(128), nullable=False)
    account_number = db.Column(db.String(64), nullable=False)
    bank_type = db.Column(db.String(64), nullable=True)
    active = db.Column(db.Integer, default=1)  # 1 = visible on donation form
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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

def generate_admin_token(name=None):
    # URLSafeTimedSerializer.dumps returns a string
    payload = {"role": "admin"}
    if name:
        payload['name'] = name
    return _token_serializer.dumps(payload)


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
# Ensure donations table has a column for proof_filename (filename of uploaded receipt) and support bank_account
# Create bank_account table for admin-managed transfer details

def create_table():
    # Ensure existing DB (created by SQLAlchemy) has the new columns we need.
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # For compatibility, check the SQLAlchemy table name 'donation'
    c.execute("PRAGMA table_info(donation)")
    cols = [r[1] for r in c.fetchall()]
    # Some older DBs may have used the plural table name 'donations' or 'images'. If so, rename them to the
    # singular table names used by the current models so our SQL queries keep working.
    if not cols:
        c.execute("PRAGMA table_info(donations)")
        if c.fetchall():
            # rename legacy plural table to singular
            c.execute("ALTER TABLE donations RENAME TO donation")
            c.execute("PRAGMA table_info(donation)")
            cols = [r[1] for r in c.fetchall()]

    # If the table doesn't exist at all, let SQLAlchemy create tables later (db.create_all was already called above),
    # otherwise add missing columns
    if cols:
        if 'proof_filename' not in cols:
            c.execute("ALTER TABLE donation ADD COLUMN proof_filename TEXT")
        if 'approved_by' not in cols:
            c.execute("ALTER TABLE donation ADD COLUMN approved_by TEXT")
        if 'approved_at' not in cols:
            c.execute("ALTER TABLE donation ADD COLUMN approved_at TEXT")
        # Add optional bank_account_id to record which account the donor chose (nullable)
        # Only add if not present
        if 'bank_account_id' not in cols:
            c.execute("ALTER TABLE donation ADD COLUMN bank_account_id INTEGER")

    # Also ensure 'image' table exists (SQLAlchemy uses singular 'image'). Rename legacy 'images' if present.
    c.execute("PRAGMA table_info(image)")
    img_cols = c.fetchall()
    if not img_cols:
        # check legacy plural
        c.execute("PRAGMA table_info(images)")
        if c.fetchall():
            c.execute("ALTER TABLE images RENAME TO image")
            c.execute("PRAGMA table_info(image)")
            img_cols = c.fetchall()
    if not img_cols:
        c.execute("""
            CREATE TABLE IF NOT EXISTS image (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                title TEXT,
                taken_at TEXT,
                uploaded_at TEXT
            )
        """)

    # Ensure bank_account table exists; accept legacy plural name 'bank_accounts' if present
    c.execute("PRAGMA table_info(bank_account)")
    bank_cols = c.fetchall()
    if not bank_cols:
        c.execute("PRAGMA table_info(bank_accounts)")
        if c.fetchall():
            # rename legacy plural to singular for consistency
            c.execute("ALTER TABLE bank_accounts RENAME TO bank_account")
            c.execute("PRAGMA table_info(bank_account)")
            bank_cols = c.fetchall()
    if not bank_cols:
        c.execute("""
            CREATE TABLE IF NOT EXISTS bank_account (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_name TEXT,
                account_name TEXT,
                account_number TEXT,
                bank_type TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT
            )
        """)

    conn.commit()
    conn.close()

create_table()

# Log each incoming request briefly to help diagnose 405s (kept lightweight)
@app.before_request
def log_request_info():
    try:
        app.logger.info(f"Incoming request: method={request.method} path={request.path} origin={request.headers.get('Origin')} content-type={request.headers.get('Content-Type')}")
    except Exception:
        pass

# Determine the actual table names used on disk (support legacy plural table names)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("PRAGMA table_info(donation)")
if c.fetchall():
    DONATION_TABLE = 'donation'
else:
    c.execute("PRAGMA table_info(donations)")
    if c.fetchall():
        # Attempt to rename the legacy plural table to the singular name used by models
        try:
            c.execute("ALTER TABLE donations RENAME TO donation")
            conn.commit()
            DONATION_TABLE = 'donation'
        except Exception:
            # If rename fails, fall back to plural name
            DONATION_TABLE = 'donations'
    else:
        # default to singular (will be created by SQLAlchemy later)
        DONATION_TABLE = 'donation'

c.execute("PRAGMA table_info(image)")
if c.fetchall():
    IMAGE_TABLE = 'image'
else:
    c.execute("PRAGMA table_info(images)")
    if c.fetchall():
        # Attempt rename to singular image table if possible
        try:
            c.execute("ALTER TABLE images RENAME TO image")
            conn.commit()
            IMAGE_TABLE = 'image'
        except Exception:
            IMAGE_TABLE = 'images'
    else:
        IMAGE_TABLE = 'image'

# bank_account table resolution (support legacy plural 'bank_accounts')
c.execute("PRAGMA table_info(bank_account)")
if c.fetchall():
    BANK_ACCOUNT_TABLE = 'bank_account'
else:
    c.execute("PRAGMA table_info(bank_accounts)")
    if c.fetchall():
        try:
            c.execute("ALTER TABLE bank_accounts RENAME TO bank_account")
            conn.commit()
            BANK_ACCOUNT_TABLE = 'bank_account'
        except Exception:
            BANK_ACCOUNT_TABLE = 'bank_accounts'
    else:
        BANK_ACCOUNT_TABLE = 'bank_account'

conn.close()

# Ensure SQLAlchemy models map to the actual table names found on disk (helps when DB has legacy plural tables)
try:
    if hasattr(Donation, '__table__') and Donation.__table__.name != DONATION_TABLE:
        Donation.__table__.name = DONATION_TABLE
    if hasattr(Image, '__table__') and Image.__table__.name != IMAGE_TABLE:
        Image.__table__.name = IMAGE_TABLE
    # Set bank account table name if present
    if hasattr(BankAccount, '__table__') and BankAccount.__table__.name != BANK_ACCOUNT_TABLE:
        BankAccount.__table__.name = BANK_ACCOUNT_TABLE

    # reflect updated names
    db.metadata.clear()
    db.reflect(bind=db.engine)
except Exception as e:
    app.logger.warning(f"Failed to remap SQLAlchemy tables: {e}")


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

    # optional: record which bank account donor chose (not required)
    bank_account_id = flask_request.form.get('bank_account_id')
    try:
        bank_account_id = int(bank_account_id) if bank_account_id is not None and bank_account_id != '' else None
    except Exception:
        bank_account_id = None

    # save donor as pending with proof filename in DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"INSERT INTO {DONATION_TABLE} (fullname, phone, amount, reference, proof_filename, status, bank_account_id) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
              (fullname, phone, amount, reference, stored_name, bank_account_id))
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
    # Use direct SQL so we are tolerant of legacy/plural table names and schema differences
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"SELECT fullname, amount, status, reference, approved_by, approved_at, bank_account_id FROM {DONATION_TABLE} WHERE reference=?", (reference,))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"message": "Reference not found"}), 404

    # bank_account_id (nullable)
    bank_account_id = row[6]
    bank_account = None
    if bank_account_id:
        try:
            c2 = conn.cursor()
            c2.execute(f"SELECT id, bank_name, account_name, account_number, bank_type FROM {BANK_ACCOUNT_TABLE} WHERE id=?", (bank_account_id,))
            br = c2.fetchone()
            if br:
                bank_account = {"id": br[0], "bank_name": br[1], "account_name": br[2], "account_number": br[3], "bank_type": br[4]}
        except Exception:
            bank_account = None

    return jsonify({
        "fullname": row[0],
        "amount": row[1],
        "status": row[2],
        "reference": row[3],
        "approved_by": row[4],
        "approved_at": row[5],
        "bank_account_id": bank_account_id,
        "bank_account": bank_account
    })
@app.route("/pending-donations", methods=["GET"])
def pending_donations():
    # Admin endpoint - requires valid admin token
    if not is_admin_authorized(request):
        return jsonify({"message": "Unauthorized"}), 401

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"SELECT fullname, phone, amount, reference, status, proof_filename, approved_by, approved_at, bank_account_id FROM {DONATION_TABLE} WHERE status='pending'")
    rows = c.fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({'fullname': r[0], 'phone': r[1], 'amount': r[2], 'reference': r[3], 'status': r[4], 'proof_filename': r[5], 'approved_by': r[6], 'approved_at': r[7], 'bank_account_id': r[8]})
    return jsonify(result)


@app.route('/paid-users', methods=['GET'])
def paid_users():
    conn = sqlite3.connect(DB_PATH)  # public endpoint: list paid donations
    c = conn.cursor()
    c.execute(f"SELECT fullname, phone, amount, reference, status, proof_filename, approved_by, approved_at, bank_account_id FROM {DONATION_TABLE} WHERE status='paid'")
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({'fullname': r[0], 'phone': r[1], 'amount': r[2], 'reference': r[3], 'status': r[4], 'proof_filename': r[5], 'approved_by': r[6], 'approved_at': r[7], 'bank_account_id': r[8]})
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
    # determine admin name (if available in token payload or header)
    admin_name = 'admin'
    # try header first
    header_name = request.headers.get('X-ADMIN-NAME')
    if header_name:
        admin_name = header_name
    else:
        # try token payload
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth.split(' ', 1)[1].strip()
            try:
                payload = _token_serializer.loads(token, max_age=ADMIN_TOKEN_EXPIRY)
                admin_name = payload.get('name', admin_name)
            except Exception:
                pass

    approved_at = datetime.utcnow().isoformat()
    c.execute("UPDATE donation SET status='paid', approved_by=?, approved_at=? WHERE reference=? AND status!='paid'", (admin_name, approved_at, reference))
    if c.rowcount == 0:
        # check if the reference exists and is already paid
        c2 = conn.cursor()
        c2.execute(f"SELECT status FROM {DONATION_TABLE} WHERE reference=?", (reference,))
        row = c2.fetchone()
        conn.close()
        if row and row[0] == 'paid':
            return jsonify({"message": "Already marked as paid"}), 200
        return jsonify({"message": "Reference not found"}), 404
    conn.commit()
    conn.close()

    return jsonify({"message": "Donation validated", "approved_by": admin_name, "approved_at": approved_at}), 200


@app.route('/admin/reset-donations', methods=['POST'])
def admin_reset_donations():
    if not is_admin_authorized(request):
        return jsonify({"message": "Unauthorized"}), 401

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"SELECT proof_filename FROM {DONATION_TABLE} WHERE proof_filename IS NOT NULL")
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

    c.execute(f"DELETE FROM {DONATION_TABLE}")
    deleted = c.rowcount
    conn.commit()
    conn.close()

    return jsonify({"message": "Donations reset", "deleted_files": deleted_files, "deleted_rows": deleted}), 200

@app.route('/admin/bank-accounts', methods=['GET','POST','OPTIONS'])
@app.route('/admin/bank-accounts/', methods=['GET','POST','OPTIONS'])
def admin_bank_accounts():
    if request.method == 'OPTIONS':
        return '', 204
    ...

    # GET - list accounts (admin-only)
    if request.method == 'GET':
        if not is_admin_authorized(request):
            return jsonify({"message": "Unauthorized"}), 401
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(f"SELECT id, bank_name, account_name, account_number, bank_type, active, created_at FROM {BANK_ACCOUNT_TABLE} ORDER BY created_at DESC")
        rows = c.fetchall()
        conn.close()
        accounts = []
        for r in rows:
            accounts.append({"id": r[0], "bank_name": r[1], "account_name": r[2], "account_number": r[3], "bank_type": r[4], "active": bool(r[5]), "created_at": r[6]})
        return jsonify(accounts)

    # POST - create new account (accept JSON or form-encoded). Token may be sent in query (?token=) or Authorization header.
    if request.method == 'POST':
        # Accept token in query string for browser friendly calls
        token_q = request.args.get('token')
        if token_q and verify_admin_token(token_q):
            authorized = True
        else:
            authorized = is_admin_authorized(request)
        if not authorized:
            return jsonify({"message": "Unauthorized"}), 401
        # Accept JSON or form body
        data = {}
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form.to_dict()
        bank_name = (data.get('bank_name') or '').strip()
        account_name = (data.get('account_name') or '').strip()
        account_number = (data.get('account_number') or '').strip()
        bank_type = data.get('bank_type') or ''
        active = 1 if (str(data.get('active', '1')).lower() in ['1','true','yes']) else 0
        if not bank_name or not account_name or not account_number:
            return jsonify({"message": "bank_name, account_name and account_number are required"}), 400
        try:
            app.logger.info(f"DB path: {DB_PATH}; exists={os.path.exists(DB_PATH)}; cwd={os.getcwd()}")
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            app.logger.info(f"Executing insert into {BANK_ACCOUNT_TABLE}")
            c.execute(f"INSERT INTO {BANK_ACCOUNT_TABLE} (bank_name, account_name, account_number, bank_type, active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                      (bank_name, account_name, account_number, bank_type, active, datetime.utcnow().isoformat()))
            conn.commit()
            inserted = c.lastrowid
            app.logger.info(f"Inserted bank account id={inserted}")
            conn.close()
            return jsonify({"message": "Added", "id": inserted}), 201
        except sqlite3.OperationalError as e:
            app.logger.error(f"OperationalError adding bank account: {e}")
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
            return jsonify({"message": "Failed to add - operational error", "error": str(e)}), 500
        except Exception as e:
            app.logger.error(f"Failed to add bank account: {e}")
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
            return jsonify({"message": "Failed to add", "error": str(e)}), 500




@app.route('/admin/bank-accounts', methods=['OPTIONS'])
@app.route('/admin/bank-accounts/', methods=['OPTIONS'])
def admin_bank_accounts_options():
    resp = app.make_response(('', 204))
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    return resp

@app.route('/admin/bank-accounts/<int:acc_id>', methods=['PUT','DELETE'])
@app.route('/admin/bank-accounts/<int:acc_id>/', methods=['PUT','DELETE'])
def admin_bank_account_item(acc_id):
    app.logger.info(f"admin_bank_account_item called: method={request.method} path={request.path} origin={request.headers.get('Origin')}")
    # Accept token in query string or Authorization header
    token_q = request.args.get('token')
    if token_q and verify_admin_token(token_q):
        authorized = True
    else:
        authorized = is_admin_authorized(request)
    if not authorized:
        return jsonify({"message": "Unauthorized"}), 401

    if request.method == 'DELETE':
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(f"DELETE FROM {BANK_ACCOUNT_TABLE} WHERE id = ?", (acc_id,))
            deleted = c.rowcount
            conn.commit()
            conn.close()
            if deleted == 0:
                return jsonify({"message": "Not found"}), 404
            return jsonify({"message": "Deleted"}), 200
        except Exception as e:
            app.logger.error(f"Failed to delete bank account {acc_id}: {e}")
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
            return jsonify({"message": "Failed to delete", "error": str(e)}), 500

    # PUT - update
    if request.method == 'PUT':
        data = {}
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form.to_dict()
        fields = []
        params = []
        for k in ['bank_name', 'account_name', 'account_number', 'bank_type']:
            if k in data:
                fields.append(f"{k} = ?")
                params.append(data[k])
        if 'active' in data:
            fields.append("active = ?")
            params.append(1 if str(data['active']).lower() in ['1','true','yes'] else 0)
        if not fields:
            return jsonify({"message": "No fields to update"}), 400
        params.append(acc_id)
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(f"UPDATE {BANK_ACCOUNT_TABLE} SET {', '.join(fields)} WHERE id = ?", params)
            conn.commit()
            conn.close()
            return jsonify({"message": "Updated"}), 200
        except Exception as e:
            app.logger.error(f"Failed to update bank account {acc_id}: {e}")
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
            return jsonify({"message": "Failed to update", "error": str(e)}), 500


@app.route('/admin/bank-accounts/<int:acc_id>', methods=['DELETE'])
def admin_delete_bank_account(acc_id):
    if not is_admin_authorized(request):
        return jsonify({"message": "Unauthorized"}), 401
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(f"DELETE FROM {BANK_ACCOUNT_TABLE} WHERE id = ?", (acc_id,))
        deleted = c.rowcount
        conn.commit()
        conn.close()
        if deleted == 0:
            return jsonify({"message": "Not found"}), 404
        return jsonify({"message": "Deleted"}), 200
    except Exception as e:
        app.logger.error(f"Failed to delete bank account {acc_id}: {e}")
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return jsonify({"message": "Failed to delete", "error": str(e)}), 500


# Public endpoint for active bank accounts (used by donation form)
@app.route('/bank-accounts', methods=['GET'])
@app.route('/bank-accounts/', methods=['GET'])
def list_bank_accounts():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(f"SELECT id, bank_name, account_name, account_number, bank_type FROM {BANK_ACCOUNT_TABLE} WHERE active=1 ORDER BY created_at DESC")
        rows = c.fetchall()
        conn.close()
        accounts = [{"id": r[0], "bank_name": r[1], "account_name": r[2], "account_number": r[3], "bank_type": r[4]} for r in rows]
        return jsonify(accounts)
    except Exception as e:
        app.logger.error(f"Failed to list bank accounts: {e}")
        return jsonify({"message": "Failed to fetch bank accounts", "error": str(e)}), 500


# Admin-only debug endpoint (returns DB file status and row counts) - useful for debugging issues
@app.route('/admin/_debug-db', methods=['GET'])
def admin_debug_db():
    if not is_admin_authorized(request):
        return jsonify({"message": "Unauthorized"}), 401
    try:
        info = {"cwd": os.getcwd(), "db_path": DB_PATH, "db_exists": os.path.exists(DB_PATH)}
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute(f"SELECT COUNT(*) FROM {BANK_ACCOUNT_TABLE}")
            info['bank_accounts_count'] = c.fetchone()[0]
        except Exception as e:
            info['bank_accounts_count_error'] = str(e)
        try:
            c.execute(f"SELECT id, bank_name, account_name, account_number, bank_type, active, created_at FROM {BANK_ACCOUNT_TABLE} ORDER BY created_at DESC LIMIT 5")
            info['bank_accounts_latest'] = [dict(id=r[0], bank_name=r[1], account_name=r[2], account_number=r[3], bank_type=r[4], active=r[5], created_at=r[6]) for r in c.fetchall()]
        except Exception as e:
            info['bank_accounts_latest_error'] = str(e)
        conn.close()
        return jsonify(info)
    except Exception as e:
        app.logger.error(f"Debug endpoint failed: {e}")
        return jsonify({"message": "Debug query failed", "error": str(e)}), 500


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
        c.execute(f'INSERT INTO {IMAGE_TABLE} (filename, title, taken_at, uploaded_at) VALUES (?, ?, ?, ?)',
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
    c.execute(f"SELECT id, filename, title, taken_at, uploaded_at FROM {IMAGE_TABLE} ORDER BY taken_at DESC, title ASC")
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
    username = data.get('username', None)
    if password != ADMIN_SECRET:
        return jsonify({'message': 'Unauthorized'}), 401
    token = generate_admin_token(name=username)
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
    c.execute(f"SELECT fullname, phone, amount, reference, status FROM {DONATION_TABLE}")
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
