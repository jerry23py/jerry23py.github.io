#!/usr/bin/env python3
"""
Migration script to add missing columns to images table on Render
Run this locally and it will update your Render PostgreSQL database
"""

import os
from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Load environment variables
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

app = Flask(__name__)

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

def migrate():
    """Add missing columns to images table"""
    with app.app_context():
        try:
            # Check if we're using PostgreSQL (Render uses this)
            if "postgresql" in app.config["SQLALCHEMY_DATABASE_URI"]:
                print("🔧 Migrating PostgreSQL database...")
                
                # SQL to add missing columns if they don't exist
                migration_sql = """
                ALTER TABLE images ADD COLUMN IF NOT EXISTS url VARCHAR(500);
                ALTER TABLE images ADD COLUMN IF NOT EXISTS public_id VARCHAR(255);
                """
                
                db.session.execute(db.text(migration_sql))
                db.session.commit()
                print("✓ Migration completed successfully!")
                print("✓ Added 'url' column")
                print("✓ Added 'public_id' column")
                
                # Verify columns exist
                check_sql = """
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'images'
                """
                result = db.session.execute(db.text(check_sql))
                columns = [row[0] for row in result]
                print(f"\n✓ Images table now has columns: {', '.join(sorted(columns))}")
            else:
                print("Using SQLite - running db.create_all()...")
                db.create_all()
                print("✓ Database tables created/updated successfully!")
                
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            db.session.rollback()
            return False
    
    return True

if __name__ == "__main__":
    success = migrate()
    exit(0 if success else 1)
