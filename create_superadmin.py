#!/usr/bin/env python3
"""
Script to create a default superadmin user
"""

import sys
from app import create_app
from app.models import db, User, SuperAdmin


def create_superadmin_user(username='sadmin', email='sadmin@example.com', password='sadmin@123'):
    app = create_app()
    with app.app_context():
        existing = User.query.filter_by(username=username).first()
        if existing:
            print(f"User '{username}' already exists with role '{existing.role}'.")
            if existing.role != 'superadmin':
                resp = input("Promote this user to superadmin? (y/n): ")
                if resp.lower() == 'y':
                    existing.role = 'superadmin'
                    db.session.commit()
                    # create SuperAdmin profile if missing
                    if not getattr(existing, 'superadmin_profile', None):
                        sa = SuperAdmin(user_id=existing.id)
                        db.session.add(sa)
                        db.session.commit()
                    print(f"User '{username}' promoted to superadmin.")
            return

        if User.query.filter_by(email=email).first():
            print(f"Email '{email}' already exists. Choose a different email.")
            return

        user = User(username=username, email=email, role='superadmin', is_active=True)
        user.set_password(password)
        try:
            db.session.add(user)
            db.session.commit()
            sa = SuperAdmin(user_id=user.id)
            db.session.add(sa)
            db.session.commit()
            print(f"Superadmin created: username={username} password={password}")
        except Exception as e:
            db.session.rollback()
            print(f"Error creating superadmin: {e}")


if __name__ == '__main__':
    if len(sys.argv) == 1:
        create_superadmin_user()
    elif len(sys.argv) == 4:
        create_superadmin_user(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        print("Usage: python create_superadmin.py [username email password]")
