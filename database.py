"""
database.py
-----------
Responsible for:
1. Creating a connection to the SQLite database.
2. Creating all tables if they don't already exist.
3. Seeding the default admin user if no admin is present.

This file is imported by app.py and called once at startup.
"""

import sqlite3
import os
from werkzeug.security import generate_password_hash

# Path to the SQLite database file
DB_PATH = os.path.join(os.path.dirname(__file__), 'trekking.db')


def get_db():
    """
    Opens a new database connection.
    Returns the connection object with Row factory so columns can be
    accessed by name (like a dictionary).
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets us do row['column_name']
    conn.execute("PRAGMA foreign_keys = ON")  # enforce FK constraints
    return conn


def init_db():
    """
    Creates all required tables and seeds the admin user.
    Called once when the Flask app starts.
    """
    conn = get_db()
    cursor = conn.cursor()

    # ------------------------------------------------------------------
    # TABLE: users
    # Stores Admin, Trek Staff, and regular Users (Trekkers).
    # role  : 'admin' | 'staff' | 'user'
    # status: 'active' | 'pending' | 'blacklisted'
    #         - Staff start as 'pending' until admin approves them.
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    NOT NULL UNIQUE,
            email       TEXT    NOT NULL UNIQUE,
            password    TEXT    NOT NULL,
            role        TEXT    NOT NULL DEFAULT 'user',
            status      TEXT    NOT NULL DEFAULT 'active',
            full_name   TEXT,
            phone       TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ------------------------------------------------------------------
    # TABLE: treks
    # Each trek is an event created by Admin and managed by assigned Staff.
    # status: 'Pending' | 'Approved' | 'Open' | 'Closed' | 'Completed'
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS treks (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT    NOT NULL,
            location          TEXT    NOT NULL,
            difficulty        TEXT    NOT NULL DEFAULT 'Easy',
            duration_days     INTEGER NOT NULL DEFAULT 1,
            total_slots       INTEGER NOT NULL DEFAULT 10,
            available_slots   INTEGER NOT NULL DEFAULT 10,
            assigned_staff_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            status            TEXT    NOT NULL DEFAULT 'Pending',
            start_date        DATE,
            end_date          DATE,
            description       TEXT,
            created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ------------------------------------------------------------------
    # TABLE: bookings
    # Records every trek booking made by a User (Trekker).
    # status: 'Booked' | 'Cancelled' | 'Completed'
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            trek_id      INTEGER NOT NULL REFERENCES treks(id) ON DELETE CASCADE,
            booking_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            status       TEXT     NOT NULL DEFAULT 'Booked'
        )
    """)

    # ------------------------------------------------------------------
    # SEED: Default Admin
    # Admin is pre-existing — no registration route for admin.
    # Credentials: username=admin, password=admin123
    # ------------------------------------------------------------------
    existing_admin = cursor.execute(
        "SELECT id FROM users WHERE role = 'admin'"
    ).fetchone()

    if not existing_admin:
        cursor.execute("""
            INSERT INTO users (username, email, password, role, status, full_name)
            VALUES (?, ?, ?, 'admin', 'active', 'System Admin')
        """, (
            'admin',
            'admin@trekkingapp.com',
            generate_password_hash('admin123')
        ))
        print("[DB] Default admin created: username=admin | password=admin123")

    conn.commit()
    conn.close()
    print("[DB] Database initialized successfully.")
