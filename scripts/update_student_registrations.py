"""
Create Student Registrations Table using SQLAlchemy
"""

import os
import sys

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db, StudentRegistration

# Create the Flask application
app = create_app(os.environ.get('FLASK_CONFIG', 'development'))

if __name__ == '__main__':
    with app.app_context():
        # Drop the existing table if it exists
        StudentRegistration.__table__.drop(db.engine, checkfirst=True)
        
        # Create the table with the new schema
        StudentRegistration.__table__.create(db.engine)
        
        print("✅ Student registrations table created successfully!")