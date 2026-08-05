"""
blueprints/user.py
------------------
Routes for regular Users (Trekkers).

Users can:
  - View their dashboard (available treks + their active bookings)
  - Browse all open treks with search and difficulty filter
  - Book an open trek (with overbooking prevention)
  - Cancel an active booking
  - View their complete booking history
  - Edit their profile (name, email, phone)
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db
from blueprints.helpers import login_required

# Create the Blueprint named 'user'
user_bp = Blueprint('user', __name__)


@user_bp.route('/dashboard')
@login_required('user')
def dashboard():
    """
    User dashboard.
    Shows:
    - A selection of currently open treks
    - The user's active (Booked) bookings
    """
    user_id = session['user_id']
    db = get_db()

    # Fetch up to 6 open treks that still have slots
    open_treks = db.execute("""
        SELECT * FROM treks
        WHERE status = 'Open' AND available_slots > 0
        ORDER BY start_date ASC
        LIMIT 6
    """).fetchall()

    # Fetch user's currently active bookings
    my_bookings = db.execute("""
        SELECT
            b.id AS booking_id,
            b.booking_date,
            b.status AS booking_status,
            t.name        AS trek_name,
            t.location,
            t.difficulty,
            t.start_date,
            t.end_date,
            t.status      AS trek_status
        FROM bookings b
        JOIN treks t ON b.trek_id = t.id
        WHERE b.user_id = ? AND b.status = 'Booked'
        ORDER BY b.booking_date DESC
    """, (user_id,)).fetchall()

    db.close()
    return render_template('user/dashboard.html',
        open_treks=open_treks,
        my_bookings=my_bookings
    )


@user_bp.route('/treks')
@login_required('user')
def treks():
    """
    Browse all open treks.

    Supports:
    - Text search: matches trek name or location
    - Difficulty filter: Easy / Moderate / Hard
    """
    search     = request.args.get('search', '').strip()
    difficulty = request.args.get('difficulty', '').strip()

    db = get_db()

    # Build the SQL query dynamically depending on which filters are active
    query  = "SELECT * FROM treks WHERE status = 'Open'"
    params = []

    if search:
        query  += " AND (name LIKE ? OR location LIKE ?)"
        params += [f'%{search}%', f'%{search}%']

    if difficulty:
        query  += " AND difficulty = ?"
        params += [difficulty]

    query += " ORDER BY start_date ASC"

    treks_list = db.execute(query, params).fetchall()

    # Find out which treks the user has already booked (to show a "booked" badge)
    already_booked_ids = set(
        row['trek_id'] for row in db.execute(
            "SELECT trek_id FROM bookings WHERE user_id = ? AND status = 'Booked'",
            (session['user_id'],)
        ).fetchall()
    )

    db.close()
    return render_template('user/treks.html',
        treks      = treks_list,
        booked_ids = already_booked_ids,
        search     = search,
        difficulty = difficulty
    )


@user_bp.route('/book/<int:trek_id>', methods=['POST'])
@login_required('user')
def book_trek(trek_id):
    """
    Book a trek.

    Checks:
    1. Trek exists
    2. Trek status is 'Open' (cannot book Pending/Closed/Completed treks)
    3. Available slots > 0 (prevents overbooking)
    4. User has not already booked this same trek

    If all checks pass:
    - A booking record is created with status='Booked'
    - available_slots is decremented by 1
    """
    user_id = session['user_id']
    db = get_db()

    trek = db.execute("SELECT * FROM treks WHERE id = ?", (trek_id,)).fetchone()

    if not trek:
        flash('Trek not found.', 'danger')
        db.close()
        return redirect(url_for('user.treks'))

    # Check trek is open for booking
    if trek['status'] != 'Open':
        flash('This trek is not open for booking.', 'warning')
        db.close()
        return redirect(url_for('user.treks'))

    # Check for available slots (overbooking prevention)
    if trek['available_slots'] <= 0:
        flash('Sorry, this trek is fully booked. No slots available.', 'danger')
        db.close()
        return redirect(url_for('user.treks'))

    # Check the user has not already booked this trek
    existing_booking = db.execute(
        "SELECT id FROM bookings WHERE user_id = ? AND trek_id = ? AND status = 'Booked'",
        (user_id, trek_id)
    ).fetchone()

    if existing_booking:
        flash('You have already booked this trek.', 'info')
        db.close()
        return redirect(url_for('user.treks'))

    # All checks passed — create the booking
    db.execute(
        "INSERT INTO bookings (user_id, trek_id, status) VALUES (?, ?, 'Booked')",
        (user_id, trek_id)
    )
    # Decrement the available slots count
    db.execute(
        "UPDATE treks SET available_slots = available_slots - 1 WHERE id = ?",
        (trek_id,)
    )
    db.commit()
    db.close()

    flash(f'🎉 You have successfully booked "{trek["name"]}"! Happy trekking!', 'success')
    return redirect(url_for('user.dashboard'))


@user_bp.route('/cancel/<int:booking_id>', methods=['POST'])
@login_required('user')
def cancel_booking(booking_id):
    """
    Cancel a booking.
    - Changes booking status to 'Cancelled'
    - Restores the trek's available slot count by 1

    Security: A user can only cancel their own bookings.
    """
    user_id = session['user_id']
    db = get_db()

    # Find the booking and make sure it belongs to this user
    booking = db.execute(
        "SELECT * FROM bookings WHERE id = ? AND user_id = ?",
        (booking_id, user_id)
    ).fetchone()

    if not booking:
        flash('Booking not found.', 'danger')
        db.close()
        return redirect(url_for('user.dashboard'))

    # Can only cancel a 'Booked' booking
    if booking['status'] != 'Booked':
        flash('This booking cannot be cancelled (it may already be cancelled or completed).', 'warning')
        db.close()
        return redirect(url_for('user.dashboard'))

    # Cancel the booking and restore the slot
    db.execute(
        "UPDATE bookings SET status = 'Cancelled' WHERE id = ?",
        (booking_id,)
    )
    db.execute(
        "UPDATE treks SET available_slots = available_slots + 1 WHERE id = ?",
        (booking['trek_id'],)
    )
    db.commit()
    db.close()

    flash('Your booking has been cancelled. The slot has been released.', 'info')
    return redirect(url_for('user.dashboard'))


@user_bp.route('/history')
@login_required('user')
def history():
    """
    View complete trekking history for the logged-in user.
    Shows all bookings (Booked, Cancelled, Completed) in reverse chronological order.
    """
    user_id = session['user_id']
    db = get_db()

    all_bookings = db.execute("""
        SELECT
            b.id AS booking_id,
            b.booking_date,
            b.status AS booking_status,
            t.name        AS trek_name,
            t.location,
            t.difficulty,
            t.start_date,
            t.end_date,
            t.status      AS trek_status,
            t.duration_days
        FROM bookings b
        JOIN treks t ON b.trek_id = t.id
        WHERE b.user_id = ?
        ORDER BY b.booking_date DESC
    """, (user_id,)).fetchall()

    db.close()
    return render_template('user/history.html', bookings=all_bookings)


@user_bp.route('/profile', methods=['GET', 'POST'])
@login_required('user')
def profile():
    """
    View and edit the user's profile.
    Users can update their full name, phone number, and email address.
    """
    user_id = session['user_id']
    db = get_db()

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone     = request.form.get('phone', '').strip()
        email     = request.form.get('email', '').strip()

        if not full_name or not email:
            flash('Full name and email are required.', 'warning')
        else:
            # Make sure the new email isn't already taken by someone else
            conflict = db.execute(
                "SELECT id FROM users WHERE email = ? AND id != ?",
                (email, user_id)
            ).fetchone()

            if conflict:
                flash('That email address is already in use by another account.', 'danger')
            else:
                db.execute(
                    "UPDATE users SET full_name = ?, phone = ?, email = ? WHERE id = ?",
                    (full_name, phone, email, user_id)
                )
                db.commit()
                # Update the session too so the navbar shows the new name
                session['full_name'] = full_name
                flash('Your profile has been updated!', 'success')

    # Fetch fresh user data to display
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    db.close()
    return render_template('user/profile.html', user=user)
