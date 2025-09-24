#!/usr/bin/env python3
"""
Script to create a new admin user
"""

import sys
from app import create_app
from app.models import db, User

def create_admin_user(username, email, password):
    """Create a new admin user"""
    app = create_app()
    
    with app.app_context():
        # Check if user already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            print(f"❌ User '{username}' already exists!")
            print(f"   Current role: {existing_user.role}")
            
            # Ask if we should update the role
            response = input("Do you want to promote this user to admin? (y/n): ")
            if response.lower() == 'y':
                existing_user.role = 'admin'
                db.session.commit()
                print(f"✅ User '{username}' promoted to admin!")
            return
        
        # Check if email already exists
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            print(f"❌ Email '{email}' already exists!")
            return
        
        # Create new admin user
        admin_user = User(
            username=username,
            email=email,
            role='admin',
            is_active=True
        )
        admin_user.set_password(password)
        
        try:
            db.session.add(admin_user)
            db.session.commit()
            print(f"✅ Admin user created successfully!")
            print(f"   Username: {username}")
            print(f"   Email: {email}")
            print(f"   Role: admin")
            print(f"   Password: {password}")
            print(f"\n🔐 Login credentials:")
            print(f"   URL: http://127.0.0.1:5002/auth/login")
            print(f"   Username: {username}")
            print(f"   Password: {password}")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error creating admin user: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Create default admin user
        print("Creating default admin user...")
        username = "superadmin"
        email = "superadmin@kodemapa.com"
        password = "admin123"
        create_admin_user(username, email, password)
    elif len(sys.argv) == 4:
        # Create custom admin user
        username = sys.argv[1]
        email = sys.argv[2]
        password = sys.argv[3]
        create_admin_user(username, email, password)
    else:
        print("Usage:")
        print("  python create_admin.py                          # Creates default admin")
        print("  python create_admin.py <username> <email> <password>  # Creates custom admin")
        print("\nExamples:")
        print("  python create_admin.py")
        print("  python create_admin.py myadmin admin@example.com mypassword123")
        sys.exit(1)
