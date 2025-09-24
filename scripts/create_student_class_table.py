import sys
import os

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db, StudentClass

# Create Flask app
app = create_app()

with app.app_context():
    if not db.inspect(db.engine).has_table("student_class"):
        StudentClass.__table__.create(db.engine)
        print("✅ student_class table created successfully!")
    else:
        print("⚠️ student_class table already exists.")
