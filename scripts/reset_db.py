#!/usr/bin/env python3
"""
Database Reset and Reinitialize Script
Resets the database and loads comprehensive solutions
"""

import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db
from scripts.init_db import init_database

def reset_and_initialize():
    """Reset database and reinitialize with comprehensive solutions"""
    print("🚀 KODEMAPA-EXAMPAD Database Reset & Initialization")
    print("=" * 60)
    
    app = create_app('development')
    
    with app.app_context():
        print("⚠️  Resetting database (all data will be lost)...")
        
        # Drop all tables
        db.drop_all()
        print("✅ Database reset complete")
        
        # Reinitialize with comprehensive solutions
        init_database()
        
        print("\n🎯 Database reinitialized with comprehensive solutions!")
        print("🌟 You can now test the API with much better coverage of answers and explanations.")

if __name__ == '__main__':
    reset_and_initialize()
