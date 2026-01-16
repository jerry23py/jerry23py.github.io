from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import time
import uuid
import os
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from flask import send_from_directory, abort
import logging
from itsdangerous import URLSafeTimedSerializer as Serializer, BadSignature, SignatureExpired
import cloudinary
import cloudinary.uploader
import cloudinary.api

cloudinary.config(
    cloud_name=os.getenv("dvxvfukd0"),
    api_key=os.getenv("765575621829511"),
    api_secret=os.getenv("MRqN3WA3lYjCKL99O6ZDD_PwakI"),
    secure=True
)

# Load environment variables
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# CORS Configuration
CORS(app, resources={
    r"/*": {"origins": "https://antihiv-aids-cds.onrender.com"}
}, expose_headers=['Content-Type'], supports_credentials=True, 
   allow_headers=['Content-Type', 'Authorization', 'X-ADMIN-KEY', 'X-ADMIN-NAME'])

# Database Configuration - Fixed for Render
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url or f"sqlite:///{os.path.join(basedir, 'donations.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

db = SQLAlchemy(app)

# Admin Configuration
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change_this_password")
SECRET_KEY = os.environ.get("SECRET_KEY") or os.environ.get("FLASK_SECRET") or os.urandom(24).hex()
ADMIN_TOKEN_EXPIRY = int(os.environ.get("ADMIN_TOKEN_EXPIRY", 3600))
UPLOAD_FOLDER = os.environ.get("GALLERY_FOLDER", os.path.join(os.getcwd(), "gallery_images"))
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Token serializer
_token_serializer = Serializer(SECRET_KEY, salt='admin-token')

# Database Models
class Donation(db.Model):
    __tablename__ = 'donations'
    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=True)
    phone = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    reference = db.Column(db.String(50), unique=True, nullable=False)
    status = db.Column(db.String(20), default="pending")
    proof_filename = db.Column(db.String(255), nullable=True)
    approved_by = db.Column(db.String(100), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    bank_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=True)
    idempotency_key = db.Column(db.String(100), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Image(db.Model):
    __tablename__ = 'images'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(500), nullable=True)        # to store cloudinary url
    public_id = db.Column(db.String(255), nullable=True)  # to store cloudinary public_id
    title = db.Column(db.String(255), nullable=True)
    taken_at = db.Column(db.DateTime, nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


class BankAccount(db.Model):
    __tablename__ = 'bank_accounts'
    id = db.Column(db.Integer, primary_key=True)
    bank_name = db.Column(db.String(128), nullable=False)
    account_name = db.Column(db.String(128), nullable=False)
    account_number = db.Column(db.String(64), nullable=False)
    bank_type = db.Column(db.String(64), nullable=True)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# Initialize database
with app.app_context():
    db.create_all()
    app.logger.info("Database tables created successfully")


# Helper Functions
def generate_admin_token(name=None):
    payload = {"role": "admin"}
    if name:
        payload['name'] = name
    return _token_serializer.dumps(payload)


def verify_admin_token(token):
    try:
        _token_serializer.loads(token, max_age=ADMIN_TOKEN_EXPIRY)
        return True
    except (SignatureExpired, BadSignature):
        return False


def is_admin_authorized(req):
    auth = req.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        token = auth.split(' ', 1)[1].strip()
        return verify_admin_token(token)
    
    legacy = req.headers.get('X-ADMIN-KEY', '')
    if legacy and legacy == ADMIN_PASSWORD:
        return True
    
    t = req.args.get('token')
    if t:
        return verify_admin_token(t)
    
    return False


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# Logging middleware
@app.before_request
def log_request_info():
    try:
        app.logger.info(f"Request: {request.method} {request.path} from {request.headers.get('Origin')}")
    except Exception:
        pass


# Routes
@app.route("/donate", methods=["POST"])
def donate():
    idempotency_key = request.form.get("idempotency_key", "").strip()
    if not idempotency_key:
        return jsonify({"message": "Missing idempotency key"}), 400
    
    # Check for duplicate
    existing = Donation.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        app.logger.warning(f"Duplicate donation blocked: {idempotency_key}")
        return jsonify({
            "message": "This donation was already submitted",
            "reference": existing.reference
        }), 409
    
    # Get form data
    fullname = request.form.get("fullname", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    
    try:
        amount = int(float(request.form.get("amount", 0)))
    except Exception:
        return jsonify({"message": "Invalid amount provided"}), 400
    
    # Validate input
    if not fullname or not email or not amount:
        return jsonify({"message": "Full name, email, and amount are required"}), 400
    
    # Handle proof file
    proof = request.files.get('proof')
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
    
    # Generate reference
    reference = uuid.uuid4().hex[:12]
    
    # Get bank account ID
    bank_account_id = request.form.get('bank_account_id')
    try:
        bank_account_id = int(bank_account_id) if bank_account_id else None
    except Exception:
        bank_account_id = None
    
    # Create donation record
    donation = Donation(
        fullname=fullname,
        email=email,
        phone=phone,
        amount=amount,
        reference=reference,
        proof_filename=stored_name,
        status='pending',
        bank_account_id=bank_account_id,
        idempotency_key=idempotency_key
    )
    
    db.session.add(donation)
    db.session.commit()
    
    message = (
        "Donation recorded as pending with proof of payment.\n"
        "An admin will review your proof and validate the donation once confirmed.\n"
        "Please keep the reference for follow-up."
    )
    
    return jsonify({"reference": reference, "message": message}), 201


@app.route("/donation-status/<reference>", methods=["GET"])
def donation_status(reference):
    donation = Donation.query.filter_by(reference=reference).first()
    
    if not donation:
        return jsonify({"message": "Reference not found"}), 404
    
    result = {
        "fullname": donation.fullname,
        "amount": donation.amount,
        "status": donation.status,
        "reference": donation.reference,
        "approved_by": donation.approved_by,
        "approved_at": donation.approved_at.isoformat() if donation.approved_at else None,
        "bank_account_id": donation.bank_account_id,
        "bank_account": None
    }
    
    if donation.bank_account_id:
        bank_account = BankAccount.query.get(donation.bank_account_id)
        if bank_account:
            result["bank_account"] = {
                "id": bank_account.id,
                "bank_name": bank_account.bank_name,
                "account_name": bank_account.account_name,
                "account_number": bank_account.account_number,
                "bank_type": bank_account.bank_type
            }
    
    return jsonify(result)
@app.route('/admin/reset-donations', methods=['POST'])
def reset_donations():
    if not is_admin_authorized(request):
        return jsonify({"message": "Unauthorized"}), 401

    try:
        # delete all donations
        deleted_rows = Donation.query.delete()
        db.session.commit()

        return jsonify({
            "message": "Reset successful",
            "deleted_rows": deleted_rows
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/pending-donations", methods=["GET"])
def pending_donations():
    if not is_admin_authorized(request):
        return jsonify({"message": "Unauthorized"}), 401
    
    donations = Donation.query.filter_by(status="pending").all()
    
    return jsonify([{
        "fullname": d.fullname,
        "phone": d.phone,
        "amount": d.amount,
        "reference": d.reference,
        "status": d.status,
        "proof_filename": d.proof_filename,
        "approved_by": d.approved_by,
        "approved_at": d.approved_at.isoformat() if d.approved_at else None
    } for d in donations])


@app.route("/paid-users", methods=["GET"])
def paid_users():
    donations = Donation.query.filter_by(status="paid").all()
    
    return jsonify([{
        "fullname": d.fullname,
        "phone": d.phone,
        "amount": d.amount,
        "reference": d.reference
    } for d in donations])


@app.route("/admin/validate-donation", methods=["POST"])
def validate_donation():
    if not is_admin_authorized(request):
        return jsonify({"message": "Unauthorized"}), 401
    
    data = request.get_json() or {}
    reference = data.get("reference")
    
    if not reference:
        return jsonify({"message": "Reference required"}), 400
    
    donation = Donation.query.filter_by(reference=reference).first()
    
    if not donation:
        return jsonify({"message": "Reference not found"}), 404
    
    if donation.status == "paid":
        return jsonify({"message": "Already marked as paid"}), 200
    
    admin_name = request.headers.get("X-ADMIN-NAME", "admin")
    
    donation.status = "paid"
    donation.approved_by = admin_name
    donation.approved_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        "message": "Donation validated",
        "approved_by": admin_name,
        "approved_at": donation.approved_at.isoformat()
    }), 200


@app.route('/admin/bank-accounts', methods=['GET', 'POST', 'OPTIONS'])
def admin_bank_accounts():
    if request.method == 'OPTIONS':
        resp = app.make_response(('', 204))
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-ADMIN-KEY,X-ADMIN-NAME'
        return resp
    
    if request.method == 'GET':
        if not is_admin_authorized(request):
            return jsonify({"message": "Unauthorized"}), 401
        
        accounts = BankAccount.query.order_by(BankAccount.created_at.desc()).all()
        
        return jsonify([{
            "id": a.id,
            "bank_name": a.bank_name,
            "account_name": a.account_name,
            "account_number": a.account_number,
            "bank_type": a.bank_type,
            "active": a.active,
            "created_at": a.created_at.isoformat()
        } for a in accounts])
    
    if request.method == 'POST':
        token_q = request.args.get('token')
        if token_q and verify_admin_token(token_q):
            authorized = True
        else:
            authorized = is_admin_authorized(request)
        
        if not authorized:
            return jsonify({"message": "Unauthorized"}), 401
        
        data = request.get_json() if request.is_json else request.form.to_dict()
        
        bank_name = data.get('bank_name', '').strip()
        account_name = data.get('account_name', '').strip()
        account_number = data.get('account_number', '').strip()
        bank_type = data.get('bank_type', '')
        active = str(data.get('active', '1')).lower() in ['1', 'true', 'yes']
        
        if not bank_name or not account_name or not account_number:
            return jsonify({"message": "bank_name, account_name and account_number are required"}), 400
        
        account = BankAccount(
            bank_name=bank_name,
            account_name=account_name,
            account_number=account_number,
            bank_type=bank_type,
            active=active
        )
        
        db.session.add(account)
        db.session.commit()
        
        return jsonify({"message": "Added", "id": account.id}), 201


@app.route('/admin/bank-accounts/<int:acc_id>', methods=['PUT', 'DELETE'])
def admin_bank_account_item(acc_id):
    token_q = request.args.get('token')
    if token_q and verify_admin_token(token_q):
        authorized = True
    else:
        authorized = is_admin_authorized(request)
    
    if not authorized:
        return jsonify({"message": "Unauthorized"}), 401
    
    account = BankAccount.query.get(acc_id)
    
    if not account:
        return jsonify({"message": "Not found"}), 404
    
    if request.method == 'DELETE':
        db.session.delete(account)
        db.session.commit()
        return jsonify({"message": "Deleted"}), 200
    
    if request.method == 'PUT':
        data = request.get_json() if request.is_json else request.form.to_dict()
        
        if 'bank_name' in data:
            account.bank_name = data['bank_name']
        if 'account_name' in data:
            account.account_name = data['account_name']
        if 'account_number' in data:
            account.account_number = data['account_number']
        if 'bank_type' in data:
            account.bank_type = data['bank_type']
        if 'active' in data:
            account.active = str(data['active']).lower() in ['1', 'true', 'yes']
        
        db.session.commit()
        
        return jsonify({"message": "Updated"}), 200


@app.route('/bank-accounts', methods=['GET'])
def list_bank_accounts():
    accounts = BankAccount.query.filter_by(active=True).order_by(BankAccount.created_at.desc()).all()
    
    return jsonify([{
        "id": a.id,
        "bank_name": a.bank_name,
        "account_name": a.account_name,
        "account_number": a.account_number,
        "bank_type": a.bank_type
    } for a in accounts])

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload-image', methods=['POST'])
def upload_image():
    files = request.files.getlist('file')

    if not files:
        return jsonify({'message': 'No files uploaded'}), 400

    album_title = request.form.get('album_title', '')
    album_date = request.form.get('album_date')

    uploaded_urls = []

    for f in files:
        if not f or f.filename == '':
            continue

        if not allowed_file(f.filename):
            app.logger.warning(f"Skipped unsupported file: {f.filename}")
            continue

        # Upload directly to Cloudinary
        try: 
            result = cloudinary.uploader.upload(
                f,
                folder="gallery",
                resource_type="image"
            )

            image = Image(
                filename=f.filename,
                url=result['secure_url'],          # CDN URL
                public_id=result['public_id'],     # for future delete
                title=album_title,
                taken_at=datetime.fromisoformat(album_date) if album_date else None
            )

            db.session.add(image)
            uploaded_urls.append(result['secure_url'])
        except Exception as e:
            app.logger.error(f"Upload or DB insert failed for file {f.filename}: {e}")
            continue
        
        

    db.session.commit()
    
    if len(uploaded_urls) == 0:
        return jsonify({'message': 'No valid images were uploaded'}), 400
    
    if len(uploaded_urls) == 1:
        return jsonify({'message': 'Uploaded', 'url': uploaded_urls[0], 'urls': uploaded_urls}), 201
    
    return jsonify({'message': 'Uploaded', 'urls': uploaded_urls}), 201


@app.route('/gallery', methods=['GET'])
def gallery_list():
    images = Image.query.order_by(Image.taken_at.desc(), Image.title.asc()).all()
    
    base = request.host_url.rstrip('/')
    
    return jsonify([{
        'id': img.id,
        'filename': img.filename,
        'title': img.title,
        'taken_at': img.taken_at.isoformat() if img.taken_at else None,
        'uploaded_at': img.uploaded_at.isoformat(),
        'url': f"{base}/gallery-image/{img.filename}"
    } for img in images])


@app.route('/gallery-image/<path:filename>', methods=['GET'])
def serve_gallery_image(filename):
    safe = secure_filename(filename)
    full = os.path.join(UPLOAD_FOLDER, safe)
    
    if not os.path.exists(full):
        return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'image-missing.png'
    )

    
    return send_from_directory(UPLOAD_FOLDER, safe)


@app.route('/protected-proof/<path:filename>', methods=['GET'])
def protected_proof(filename):
    if not is_admin_authorized(request):
        return jsonify({"message": "Unauthorized"}), 401
    
    safe = secure_filename(filename)
    full = os.path.join(UPLOAD_FOLDER, safe)
    
    if not os.path.exists(full):
        abort(404)
    
    return send_from_directory(UPLOAD_FOLDER, safe)

@app.route('/admin/delete-image/<int:image_id>', methods=['DELETE'])
def admin_delete_image(image_id):
    # Check if admin authorized via your helper function
    if not is_admin_authorized(request):
        return jsonify({"message": "Unauthorized"}), 401

    # Get image record from DB
    image = Image.query.get(image_id)
    if not image:
        return jsonify({"message": "Image not found"}), 404

    try:
        # Delete image from Cloudinary if public_id is stored (adjust if you store it)
        if hasattr(image, 'public_id') and image.public_id:
            cloudinary.uploader.destroy(image.public_id)
        
        # Delete from database
        db.session.delete(image)
        db.session.commit()

        return jsonify({"message": "Image deleted successfully"}), 200

    except Exception as e:
        app.logger.error(f"Failed to delete image {image_id}: {e}")
        db.session.rollback()
        return jsonify({"message": "Failed to delete image", "error": str(e)}), 500

@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json() or {}
    password = data.get('password', '')
    
    if password != ADMIN_PASSWORD:
        return jsonify({'message': 'Unauthorized'}), 401
    
    token = generate_admin_token(name="admin")
    return jsonify({'token': token, 'expires_in': ADMIN_TOKEN_EXPIRY}), 200


@app.route('/download-csv', methods=['GET'])
def download_csv():
    if not is_admin_authorized(request):
        return jsonify({"message": "Unauthorized"}), 401
    
    import csv
    from io import StringIO
    
    donations = Donation.query.all()
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['fullname', 'phone', 'amount', 'reference', 'status'])
    
    for d in donations:
        cw.writerow([d.fullname, d.phone, d.amount, d.reference, d.status])
    
    output = si.getvalue()
    
    return app.response_class(output, mimetype='text/csv', headers={
        'Content-Disposition': 'attachment; filename=donations.csv'
    })


@app.route("/")
def home():
    FRONTEND_DIR = os.path.abspath(os.path.join(basedir, '..'))
    index_path = os.path.join(FRONTEND_DIR, 'index.html')
    
    if os.path.exists(index_path):
        return send_from_directory(FRONTEND_DIR, 'index.html')
    
    return jsonify({"message": "Backend is running successfully!"})


@app.route('/<path:path>')
def serve_frontend(path):
    FRONTEND_DIR = os.path.abspath(os.path.join(basedir, '..'))
    
    candidate = os.path.join(FRONTEND_DIR, path)
    if os.path.exists(candidate):
        return send_from_directory(FRONTEND_DIR, path)
    
    candidate = os.path.join(FRONTEND_DIR, 'frontend_cds', path)
    if os.path.exists(candidate):
        return send_from_directory(os.path.join(FRONTEND_DIR, 'frontend_cds'), path)
    
    candidate = os.path.join(FRONTEND_DIR, 'image', path)
    if os.path.exists(candidate):
        return send_from_directory(os.path.join(FRONTEND_DIR, 'image'), path)
    
    abort(404)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=(os.environ.get("FLASK_DEBUG", "False") == "True"))