"""
blueprints/auth.py
------------------
Handles all authentication routes:
  GET/POST /login    — Login for Admin, Staff, and Users
  GET/POST /register — Registration for Staff and Users only (no admin reg)
  GET      /logout   — Clears session and redirects to login
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db

# Create the Blueprint object — named 'auth'
auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    GET  → Show the login form.
    POST → Validate credentials and redirect to the correct dashboard.
    """
    # If already logged in, go to the right dashboard
    if 'user_id' in session:
        role = session.get('role')
        return redirect(url_for(f'{role}.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Basic empty-field check
        if not username or not password:
            flash('Please enter both username and password.', 'warning')
            return render_template('auth/login.html')

        db = get_db()
        # Look up the user by username
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        db.close()

        # --- Validation checks ---

        # 1. Does user exist? Is the password correct?
        if not user or not check_password_hash(user['password'], password):
            flash('Invalid username or password.', 'danger')
            return render_template('auth/login.html')

        # 2. Staff must have admin approval before they can log in
        if user['role'] == 'staff' and user['status'] == 'pending':
            flash('Your account is awaiting admin approval. Please check back later.', 'warning')
            return render_template('auth/login.html')

        # 3. Blacklisted accounts cannot log in
        if user['status'] == 'blacklisted':
            flash('Your account has been suspended. Please contact the administrator.', 'danger')
            return render_template('auth/login.html')

        # --- All checks passed: set session variables ---
        session['user_id']   = user['id']
        session['username']  = user['username']
        session['role']      = user['role']
        session['full_name'] = user['full_name'] or user['username']

        flash(f"Welcome back, {session['full_name']}!", 'success')

        # Redirect to the correct dashboard based on role
        if user['role'] == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif user['role'] == 'staff':
            return redirect(url_for('staff.dashboard'))
        else:
            return redirect(url_for('user.dashboard'))

    # GET request — just show the form
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    GET  → Show the registration form.
    POST → Create a new account (Staff or User only).

    Staff accounts are set to 'pending' status after registration.
    They must wait for admin approval before they can log in.

    User accounts are set to 'active' immediately and can log in right away.
    """
    if 'user_id' in session:
        return redirect(url_for(f"{session['role']}.dashboard"))

    if request.method == 'POST':
        username  = request.form.get('username', '').strip()
        email     = request.form.get('email', '').strip()
        password  = request.form.get('password', '')
        full_name = request.form.get('full_name', '').strip()
        phone     = request.form.get('phone', '').strip()
        role      = request.form.get('role', 'user')  # 'user' or 'staff'

        # --- Input validation ---
        if not all([username, email, password, full_name]):
            flash('Please fill in all required fields.', 'warning')
            return render_template('auth/register.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'warning')
            return render_template('auth/register.html')

        # Prevent someone trying to register as admin via the form
        if role not in ('user', 'staff'):
            flash('Invalid role selected.', 'danger')
            return render_template('auth/register.html')

        db = get_db()

        # Check that username and email are not already taken
        existing = db.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?",
            (username, email)
        ).fetchone()

        if existing:
            db.close()
            flash('That username or email is already registered. Try logging in.', 'danger')
            return render_template('auth/register.html')

        # Staff start as 'pending'; users are immediately 'active'
        status = 'pending' if role == 'staff' else 'active'

        # Insert the new user into the database
        db.execute("""
            INSERT INTO users (username, email, password, role, status, full_name, phone)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            username,
            email,
            generate_password_hash(password),   # never store plain text passwords!
            role,
            status,
            full_name,
            phone
        ))
        db.commit()
        db.close()

        # Show appropriate message based on role
        if role == 'staff':
            flash('Registration successful! Your account is pending admin approval. You will be able to log in once approved.', 'info')
        else:
            flash('Registration successful! You can now log in.', 'success')

        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/logout')
def logout():
    """Clears all session data and redirects to the login page."""
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))
