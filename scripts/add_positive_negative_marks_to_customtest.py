"""
Migration script to add positive_marks and negative_marks columns to customTests table
"""
from app import db, create_app
from sqlalchemy import text

def upgrade():
    with create_app().app_context():
        with db.engine.connect() as conn:
            # Add positive_marks column if not exists
            try:
                conn.execute(text('ALTER TABLE customTests ADD COLUMN positive_marks INTEGER DEFAULT 1'))
            except Exception:
                pass  # Ignore if already exists
            try:
                conn.execute(text('ALTER TABLE customTests ADD COLUMN negative_marks INTEGER DEFAULT 0'))
            except Exception:
                pass  # Ignore if already exists
            print("Migration complete: Added positive_marks and negative_marks columns to customTests.")

if __name__ == "__main__":
    upgrade()