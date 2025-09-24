import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db

app = create_app()

with app.app_context():
    if db.inspect(db.engine).has_table("student_class"):
        db.metadata.tables['student_class'].drop(db.engine)
        print("🗑️ student_class table deleted successfully!")
    else:
        print("⚠️ student_class table does not exist.")
