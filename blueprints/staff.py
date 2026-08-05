"""
blueprints/staff.py
-------------------
Routes for Trek Staff members.

Staff can:
  - View their dashboard showing treks assigned to them by Admin
  - Open a trek detail page where they can:
      * Update available slots
      * Change trek status (Open / Closed / Completed)
      * View the list of registered participants
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db
from blueprints.helpers import login_required

# Create the Blueprint named 'staff'
staff_bp = Blueprint('staff', __name__)


@staff_bp.route('/dashboard')
@login_required('staff')
def dashboard():
    """
    Staff dashboard.
    Shows all treks that the admin has assigned to this staff member,
    along with how many users have booked each trek.
    """
    staff_id = session['user_id']
    db = get_db()

    # Get treks assigned to this staff member
    # Also count how many users have a 'Booked' booking for each trek
    assigned_treks = db.execute("""
        SELECT
            t.*,
            (SELECT COUNT(*) FROM bookings b
             WHERE b.trek_id = t.id AND b.status = 'Booked') AS booked_count
        FROM treks t
        WHERE t.assigned_staff_id = ?
        ORDER BY t.start_date ASC
    """, (staff_id,)).fetchall()

    db.close()
    return render_template('staff/dashboard.html', treks=assigned_treks)


@staff_bp.route('/trek/<int:trek_id>', methods=['GET', 'POST'])
@login_required('staff')
def trek_detail(trek_id):
    """
    Trek detail page for staff.

    GET  → Show trek info and list of participants.
    POST → Handle one of two actions via a hidden 'action' field:
             action='update_slots'  → Update available_slots
             action='update_status' → Change trek status

    Security: Only the assigned staff member can access this page.
    If another staff member tries to access it, they are redirected.
    """
    staff_id = session['user_id']
    db = get_db()

    # Verify this trek is actually assigned to the current staff member
    trek = db.execute(
        "SELECT * FROM treks WHERE id = ? AND assigned_staff_id = ?",
        (trek_id, staff_id)
    ).fetchone()

    if not trek:
        db.close()
        flash('Trek not found or you are not assigned to this trek.', 'danger')
        return redirect(url_for('staff.dashboard'))

    if request.method == 'POST':
        action = request.form.get('action')

        # ── Action 1: Update Available Slots ──────────────────────────────
        if action == 'update_slots':
            try:
                new_slots = int(request.form.get('available_slots', trek['available_slots']))

                if new_slots < 0:
                    flash('Slots cannot be a negative number.', 'warning')
                elif new_slots > trek['total_slots']:
                    flash(
                        f'Available slots cannot exceed total slots ({trek["total_slots"]}).',
                        'warning'
                    )
                else:
                    db.execute(
                        "UPDATE treks SET available_slots = ? WHERE id = ?",
                        (new_slots, trek_id)
                    )
                    db.commit()
                    flash('Available slots updated successfully!', 'success')

            except ValueError:
                flash('Please enter a valid number for slots.', 'danger')

        # ── Action 2: Update Trek Status ──────────────────────────────────
        elif action == 'update_status':
            new_status = request.form.get('status')
            # Staff can only set these statuses (not Pending/Approved — that's admin's job)
            allowed_statuses = ('Open', 'Closed', 'Completed')

            if new_status in allowed_statuses:
                db.execute(
                    "UPDATE treks SET status = ? WHERE id = ?",
                    (new_status, trek_id)
                )
                # If trek is marked as Completed, mark all active Booked bookings for this trek as Completed
                if new_status == 'Completed':
                    db.execute(
                        "UPDATE bookings SET status = 'Completed' WHERE trek_id = ? AND status = 'Booked'",
                        (trek_id,)
                    )
                db.commit()
                flash(f'Trek status changed to "{new_status}".', 'success')
            else:
                flash('Invalid status value.', 'danger')

        # Re-fetch the trek so the page shows updated data
        trek = db.execute(
            "SELECT * FROM treks WHERE id = ?", (trek_id,)
        ).fetchone()

    # Get the list of all users who have booked this trek
    participants = db.execute("""
        SELECT
            u.full_name,
            u.username,
            u.email,
            u.phone,
            b.booking_date,
            b.status AS booking_status
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        WHERE b.trek_id = ?
        ORDER BY b.booking_date ASC
    """, (trek_id,)).fetchall()

    db.close()
    return render_template('staff/trek_detail.html', trek=trek, participants=participants)
