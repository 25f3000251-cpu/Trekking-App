"""
blueprints/helpers.py
---------------------
Contains the login_required decorator used to protect routes.

Usage:
    @login_required()           # any logged-in user
    @login_required('admin')    # admin only
    @login_required('staff')    # staff only
    @login_required('user')     # trekker only
"""

from functools import wraps
from flask import session, redirect, url_for, flash
from database import get_db


def login_required(role=None):
    """
    A decorator that protects Flask routes from unauthorized access.

    How it works:
    1. Checks if 'user_id' exists in the session (i.e., user is logged in).
    2. If a role is specified, checks that the session role matches.
    3. Queries the DB to ensure the user hasn't been blacklisted or revoked mid-session.
    4. If any check fails, clears the session and redirects to login.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Step 1: Is the user logged in?
            if 'user_id' not in session:
                flash('Please log in to continue.', 'warning')
                return redirect(url_for('auth.login'))

            # Step 2: Does the user have the required role?
            if role and session.get('role') != role:
                flash('You do not have permission to access that page.', 'danger')
                return redirect(url_for('auth.login'))

            # Step 3: Check database for account status (re-check blacklist/pending status)
            db = get_db()
            user = db.execute(
                "SELECT status, role FROM users WHERE id = ?", (session['user_id'],)
            ).fetchone()
            db.close()

            if not user or user['status'] == 'blacklisted':
                session.clear()
                flash('Your account has been suspended or deleted.', 'danger')
                return redirect(url_for('auth.login'))

            if user['role'] == 'staff' and user['status'] == 'pending':
                session.clear()
                flash('Your account is awaiting admin approval.', 'warning')
                return redirect(url_for('auth.login'))

            # All checks passed — proceed to the actual route function
            return f(*args, **kwargs)
        return wrapper
    return decorator

