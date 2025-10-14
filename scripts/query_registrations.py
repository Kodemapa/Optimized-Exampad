"""
Query Student Registrations
"""

import os
import sys

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db

# Create the Flask application
app = create_app(os.environ.get('FLASK_CONFIG', 'development'))

if __name__ == '__main__':
    with app.app_context():
        # Query all student registrations
        with db.engine.connect() as conn:
            result = conn.execute(db.text('SELECT * FROM student_registrations'))
            rows = result.fetchall()
            
            print("\nExisting Student Registrations:")
            print("-" * 50)
            for row in rows:
                print(f"Application No: {row.application_no}")
                print(f"Student Name: {row.student_name}")
                print(f"Contact: {row.contact_1}")
                print("-" * 50)