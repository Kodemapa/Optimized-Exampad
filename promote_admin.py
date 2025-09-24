#!/usr/bin/env python3
"""
Script to promote a user to admin role
"""

import sys
from app import create_app
from app.models import db, User

def promote_user_to_admin(username):
    """Promote a user to admin role"""
    app = create_app()
    
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if user:
            user.role = 'admin'
            db.session.commit()
            print(f"✅ User '{username}' promoted to admin successfully!")
            print(f"   Email: {user.email}")
            print(f"   Role: {user.role}")
        else:
            print(f"❌ User '{username}' not found!")
            
            # List available users
            all_users = User.query.all()
            if all_users:
                print("\nAvailable users:")
                for u in all_users:
                    print(f"   - {u.username} ({u.email}) - Role: {u.role}")
            else:
                print("No users found in database.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python promote_admin.py <username>")
        print("Example: python promote_admin.py john_doe")
        sys.exit(1)
    
    username = sys.argv[1]
    promote_user_to_admin(username)
