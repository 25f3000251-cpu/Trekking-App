"""
app.py
------
Main Flask application file.

- Creates the Flask app
- Registers all Blueprints (auth, admin, staff, user)
- Initializes the database on first run
- Runs the development server
"""

from flask import Flask, redirect, url_for
from database import init_db

# ── Import Blueprints ────────────────────────────────────────────────────────
from blueprints.auth  import auth_bp
from blueprints.admin import admin_bp
from blueprints.staff import staff_bp
from blueprints.user  import user_bp

# ── Create Flask Application ─────────────────────────────────────────────────
app = Flask(__name__)

# Secret key is used to sign session cookies.
# In a real production app, store this in an environment variable.
app.secret_key = 'trek-secret-key-2024'

# ── Register Blueprints ───────────────────────────────────────────────────────
# Each blueprint handles its own URL prefix and routes.
app.register_blueprint(auth_bp)          # /login, /register, /logout
app.register_blueprint(admin_bp, url_prefix='/admin')  # /admin/...
app.register_blueprint(staff_bp, url_prefix='/staff')  # /staff/...
app.register_blueprint(user_bp,  url_prefix='/user')   # /user/...


# ── Root Route ────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    """Landing page — redirects to login."""
    return redirect(url_for('auth.login'))


# ── App Entry Point ───────────────────────────────────────────────────────────
if __name__ == '__main__':
    # Initialize database (create tables + seed admin) before starting server
    init_db()
    app.run(debug=True)
