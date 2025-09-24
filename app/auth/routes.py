from app.auth import bp
@bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        if not username or not new_password or not confirm_password:
            flash('All fields are required.', 'danger')
            return render_template('auth/forgot_password.html')
        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/forgot_password.html')
        user = User.query.filter_by(username=username).first()
        if not user:
            flash('Username does not exist.', 'danger')
            return render_template('auth/forgot_password.html')
        user.set_password(new_password)
        db.session.commit()
        flash('Password changed successfully! Please log in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html')
"""
Authentication Routes - Login, Register, Logout
"""

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.auth import bp
from app.models import db, User

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user, remember=request.form.get('remember'))
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('main.dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('auth/login.html')

@bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'student')

        # Check if user already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('auth/register.html')

        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return render_template('auth/register.html')

        # Create new user with role
        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')

@bp.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('auth.login'))

@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        new_name = request.form.get('name')
        new_username = request.form.get('username')
        if new_name:
            current_user.name = new_name
        if new_username:
            current_user.username = new_username
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('auth.profile'))
    return render_template('profile.html', user=current_user)


from flask import jsonify, request
from flask_login import login_required, current_user
from app.models import db, User

@bp.route('/update_username', methods=['POST'])
@login_required
def update_username():
    data = request.get_json()
    new_username = data.get('username', '').strip()
    if not new_username:
        return jsonify({'success': False, 'message': 'Username cannot be empty.'}), 400
    if new_username == current_user.username:
        return jsonify({'success': True})
    if User.query.filter_by(username=new_username).first():
        return jsonify({'success': False, 'message': 'Username already exists.'}), 409
    # Update username in the database
    user = User.query.get(current_user.id)
    user.username = new_username
    db.session.commit()
    return jsonify({'success': True})
