"""
blueprints/admin.py
-------------------
All routes for the Admin role.

Admin can:
  - View dashboard with overall statistics
  - Create, edit, and delete treks
  - Approve, blacklist, or re-activate staff members
  - Assign staff to treks (done via the trek edit form)
  - View and manage user accounts
  - Search treks, staff, and users by name or ID
  - View all bookings across all treks
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db
from blueprints.helpers import login_required

# Create the Blueprint named 'admin'
admin_bp = Blueprint('admin', __name__)


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route('/dashboard')
@login_required('admin')
def dashboard():
    """
    Admin dashboard.
    Shows a summary of the entire system:
    - Total treks, users, staff, bookings
    - Pending staff approval count
    - Recent treks list
    - Trek booking counts (used for a chart)
    """
    db = get_db()

    total_treks    = db.execute("SELECT COUNT(*) FROM treks").fetchone()[0]
    total_users    = db.execute("SELECT COUNT(*) FROM users WHERE role = 'user'").fetchone()[0]
    total_staff    = db.execute("SELECT COUNT(*) FROM users WHERE role = 'staff'").fetchone()[0]
    total_bookings = db.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    pending_staff  = db.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'staff' AND status = 'pending'"
    ).fetchone()[0]

    # Most recently created treks
    recent_treks = db.execute("""
        SELECT t.*, u.full_name as staff_name
        FROM treks t
        LEFT JOIN users u ON t.assigned_staff_id = u.id
        ORDER BY t.created_at DESC
        LIMIT 5
    """).fetchall()

    # For the chart: top 6 treks by number of bookings
    trek_stats = db.execute("""
        SELECT t.name, COUNT(b.id) as booking_count
        FROM treks t
        LEFT JOIN bookings b ON t.id = b.trek_id AND b.status = 'Booked'
        GROUP BY t.id
        ORDER BY booking_count DESC
        LIMIT 6
    """).fetchall()

    db.close()

    return render_template('admin/dashboard.html',
        total_treks    = total_treks,
        total_users    = total_users,
        total_staff    = total_staff,
        total_bookings = total_bookings,
        pending_staff  = pending_staff,
        recent_treks   = recent_treks,
        trek_stats     = trek_stats
    )


# ─────────────────────────────────────────────────────────────────────────────
# TREK MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route('/treks')
@login_required('admin')
def treks():
    """
    List all treks.
    Supports searching by trek name, location, or ID via a GET parameter ?search=
    """
    search = request.args.get('search', '').strip()
    db = get_db()

    if search:
        # Search by name, location, or numeric ID
        treks_list = db.execute("""
            SELECT t.*, u.full_name AS staff_name
            FROM treks t
            LEFT JOIN users u ON t.assigned_staff_id = u.id
            WHERE t.name LIKE ?
               OR t.location LIKE ?
               OR CAST(t.id AS TEXT) = ?
            ORDER BY t.created_at DESC
        """, (f'%{search}%', f'%{search}%', search)).fetchall()
    else:
        treks_list = db.execute("""
            SELECT t.*, u.full_name AS staff_name
            FROM treks t
            LEFT JOIN users u ON t.assigned_staff_id = u.id
            ORDER BY t.created_at DESC
        """).fetchall()

    db.close()
    return render_template('admin/treks.html', treks=treks_list, search=search)


@admin_bp.route('/trek/add', methods=['GET', 'POST'])
@login_required('admin')
def add_trek():
    """
    GET  → Show the blank add-trek form.
    POST → Validate and insert a new trek into the database.
    """
    db = get_db()

    if request.method == 'POST':
        name          = request.form.get('name', '').strip()
        location      = request.form.get('location', '').strip()
        difficulty    = request.form.get('difficulty', 'Easy')
        duration_days = request.form.get('duration_days', 1)
        total_slots   = request.form.get('total_slots', 10)
        status        = request.form.get('status', 'Pending')
        start_date    = request.form.get('start_date') or None
        end_date      = request.form.get('end_date') or None
        description   = request.form.get('description', '').strip()
        staff_id      = request.form.get('assigned_staff_id') or None

        if not name or not location:
            flash('Trek name and location are required.', 'warning')
        else:
            try:
                duration_days = int(request.form.get('duration_days', 1))
                total_slots   = int(request.form.get('total_slots', 10))
                if duration_days < 1 or total_slots < 1:
                    raise ValueError("Duration and slots must be positive.")
            except ValueError:
                flash('Please enter valid numeric values for duration and total slots.', 'warning')
            else:
                db.execute("""
                    INSERT INTO treks
                        (name, location, difficulty, duration_days, total_slots,
                         available_slots, assigned_staff_id, status,
                         start_date, end_date, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    name, location, difficulty, duration_days,
                    total_slots, total_slots,  # available_slots starts equal to total
                    staff_id, status,
                    start_date, end_date, description
                ))
                db.commit()
                db.close()
                flash(f'Trek "{name}" has been created!', 'success')
                return redirect(url_for('admin.treks'))

    # Load approved+active staff for the dropdown
    staff_list = db.execute(
        "SELECT id, full_name FROM users WHERE role = 'staff' AND status = 'active'"
    ).fetchall()
    db.close()

    return render_template('admin/trek_form.html', trek=None, staff_list=staff_list)


@admin_bp.route('/trek/edit/<int:trek_id>', methods=['GET', 'POST'])
@login_required('admin')
def edit_trek(trek_id):
    """
    GET  → Show the edit form pre-filled with existing trek data.
    POST → Validate and update the trek.
    """
    db = get_db()
    trek = db.execute("SELECT * FROM treks WHERE id = ?", (trek_id,)).fetchone()

    if not trek:
        db.close()
        flash('Trek not found.', 'danger')
        return redirect(url_for('admin.treks'))

    if request.method == 'POST':
        name        = request.form.get('name', '').strip()
        location    = request.form.get('location', '').strip()
        difficulty  = request.form.get('difficulty', 'Easy')
        status      = request.form.get('status', 'Pending')
        start_date  = request.form.get('start_date') or None
        end_date    = request.form.get('end_date') or None
        description = request.form.get('description', '').strip()
        staff_id    = request.form.get('assigned_staff_id') or None

        try:
            duration_days = int(request.form.get('duration_days', 1))
            total_slots   = int(request.form.get('total_slots', 10))
            if duration_days < 1 or total_slots < 1:
                raise ValueError("Duration and slots must be positive.")
        except ValueError:
            flash('Please enter valid numeric values for duration and total slots.', 'warning')
        else:
            # Recalculate available slots based on current 'Booked' bookings
            booked_count = db.execute(
                "SELECT COUNT(*) FROM bookings WHERE trek_id = ? AND status = 'Booked'",
                (trek_id,)
            ).fetchone()[0]
            available_slots = max(0, total_slots - booked_count)

            db.execute("""
                UPDATE treks SET
                    name = ?, location = ?, difficulty = ?,
                    duration_days = ?, total_slots = ?, available_slots = ?,
                    assigned_staff_id = ?, status = ?,
                    start_date = ?, end_date = ?, description = ?
                WHERE id = ?
            """, (
                name, location, difficulty, duration_days, total_slots, available_slots,
                staff_id, status, start_date, end_date, description, trek_id
            ))

            # If status is set to Completed, update active bookings for this trek to Completed
            if status == 'Completed':
                db.execute(
                    "UPDATE bookings SET status = 'Completed' WHERE trek_id = ? AND status = 'Booked'",
                    (trek_id,)
                )

            db.commit()
            db.close()
            flash(f'Trek "{name}" updated successfully!', 'success')
            return redirect(url_for('admin.treks'))

    # GET: load staff list for dropdown
    staff_list = db.execute(
        "SELECT id, full_name FROM users WHERE role = 'staff' AND status = 'active'"
    ).fetchall()
    db.close()

    return render_template('admin/trek_form.html', trek=trek, staff_list=staff_list)


@admin_bp.route('/trek/delete/<int:trek_id>', methods=['POST'])
@login_required('admin')
def delete_trek(trek_id):
    """Delete a trek and all its associated bookings (via CASCADE)."""
    db = get_db()
    trek = db.execute("SELECT name FROM treks WHERE id = ?", (trek_id,)).fetchone()

    if trek:
        db.execute("DELETE FROM treks WHERE id = ?", (trek_id,))
        db.commit()
        flash(f'Trek "{trek["name"]}" has been deleted.', 'success')
    else:
        flash('Trek not found.', 'danger')

    db.close()
    return redirect(url_for('admin.treks'))


# ─────────────────────────────────────────────────────────────────────────────
# STAFF MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route('/staff')
@login_required('admin')
def staff():
    """
    List all registered staff members.
    Supports search by name, username, or ID.
    """
    search = request.args.get('search', '').strip()
    db = get_db()

    if search:
        staff_list = db.execute("""
            SELECT u.*, COUNT(t.id) AS trek_count
            FROM users u
            LEFT JOIN treks t ON u.id = t.assigned_staff_id
            WHERE u.role = 'staff'
              AND (u.full_name LIKE ? OR u.username LIKE ? OR CAST(u.id AS TEXT) = ?)
            GROUP BY u.id
            ORDER BY u.created_at DESC
        """, (f'%{search}%', f'%{search}%', search)).fetchall()
    else:
        staff_list = db.execute("""
            SELECT u.*, COUNT(t.id) AS trek_count
            FROM users u
            LEFT JOIN treks t ON u.id = t.assigned_staff_id
            WHERE u.role = 'staff'
            GROUP BY u.id
            ORDER BY u.created_at DESC
        """).fetchall()

    db.close()
    return render_template('admin/staff.html', staff_list=staff_list, search=search)


@admin_bp.route('/staff/approve/<int:staff_id>', methods=['POST'])
@login_required('admin')
def approve_staff(staff_id):
    """Approve a pending staff member — allows them to log in."""
    db = get_db()
    db.execute(
        "UPDATE users SET status = 'active' WHERE id = ? AND role = 'staff'",
        (staff_id,)
    )
    db.commit()
    db.close()
    flash('Staff member approved! They can now log in.', 'success')
    return redirect(url_for('admin.staff'))


@admin_bp.route('/staff/blacklist/<int:staff_id>', methods=['POST'])
@login_required('admin')
def blacklist_staff(staff_id):
    """Blacklist a staff member — prevents them from logging in."""
    db = get_db()
    db.execute(
        "UPDATE users SET status = 'blacklisted' WHERE id = ? AND role = 'staff'",
        (staff_id,)
    )
    db.commit()
    db.close()
    flash('Staff member has been blacklisted.', 'warning')
    return redirect(url_for('admin.staff'))


@admin_bp.route('/staff/activate/<int:staff_id>', methods=['POST'])
@login_required('admin')
def activate_staff(staff_id):
    """Re-activate a blacklisted staff member."""
    db = get_db()
    db.execute(
        "UPDATE users SET status = 'active' WHERE id = ? AND role = 'staff'",
        (staff_id,)
    )
    db.commit()
    db.close()
    flash('Staff member re-activated.', 'success')
    return redirect(url_for('admin.staff'))


# ─────────────────────────────────────────────────────────────────────────────
# USER MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route('/users')
@login_required('admin')
def users():
    """
    List all registered Trekkers (users).
    Supports search by name, username, or ID.
    """
    search = request.args.get('search', '').strip()
    db = get_db()

    if search:
        users_list = db.execute("""
            SELECT u.*, COUNT(b.id) AS booking_count
            FROM users u
            LEFT JOIN bookings b ON u.id = b.user_id
            WHERE u.role = 'user'
              AND (u.full_name LIKE ? OR u.username LIKE ? OR CAST(u.id AS TEXT) = ?)
            GROUP BY u.id
            ORDER BY u.created_at DESC
        """, (f'%{search}%', f'%{search}%', search)).fetchall()
    else:
        users_list = db.execute("""
            SELECT u.*, COUNT(b.id) AS booking_count
            FROM users u
            LEFT JOIN bookings b ON u.id = b.user_id
            WHERE u.role = 'user'
            GROUP BY u.id
            ORDER BY u.created_at DESC
        """).fetchall()

    db.close()
    return render_template('admin/users.html', users=users_list, search=search)


@admin_bp.route('/user/blacklist/<int:user_id>', methods=['POST'])
@login_required('admin')
def blacklist_user(user_id):
    """Blacklist a user account."""
    db = get_db()
    db.execute(
        "UPDATE users SET status = 'blacklisted' WHERE id = ? AND role = 'user'",
        (user_id,)
    )
    db.commit()
    db.close()
    flash('User has been blacklisted.', 'warning')
    return redirect(url_for('admin.users'))


@admin_bp.route('/user/activate/<int:user_id>', methods=['POST'])
@login_required('admin')
def activate_user(user_id):
    """Re-activate a blacklisted user account."""
    db = get_db()
    db.execute(
        "UPDATE users SET status = 'active' WHERE id = ? AND role = 'user'",
        (user_id,)
    )
    db.commit()
    db.close()
    flash('User account has been re-activated.', 'success')
    return redirect(url_for('admin.users'))


# ─────────────────────────────────────────────────────────────────────────────
# BOOKINGS
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route('/bookings')
@login_required('admin')
def bookings():
    """View all bookings across all treks and all users."""
    db = get_db()
    bookings_list = db.execute("""
        SELECT
            b.id,
            b.booking_date,
            b.status      AS booking_status,
            u.username,
            u.full_name,
            t.name        AS trek_name,
            t.location,
            t.difficulty,
            t.status      AS trek_status
        FROM bookings b
        JOIN users u ON b.user_id  = u.id
        JOIN treks t ON b.trek_id  = t.id
        ORDER BY b.booking_date DESC
    """).fetchall()
    db.close()
    return render_template('admin/bookings.html', bookings=bookings_list)
