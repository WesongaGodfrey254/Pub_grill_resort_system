from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from sqlalchemy import and_
from ..extensions import db, emit_event
from ..models import Room, RoomBooking, RoomBlock, Notification, AuditLog

rooms_bp = Blueprint("rooms", __name__)

ACTIVE_BOOKING_STATES = ("confirmed", "checked_in")

def parse_dt(value):
    # Datetimes are stored as naive UTC. Browser-local values are interpreted in the configured business timezone in a future timezone-aware deployment.
    return datetime.fromisoformat(value)

def room_is_available(room_id, start, end):
    room = db.session.get(Room, room_id)
    if not room or room.status == "maintenance":
        return False
    booking = RoomBooking.query.filter(
        RoomBooking.room_id == room_id,
        RoomBooking.status.in_(ACTIVE_BOOKING_STATES),
        RoomBooking.check_in_at < end,
        RoomBooking.check_out_at > start
    ).first()
    block = RoomBlock.query.filter_by(room_id=room_id, is_active=True).filter(
        RoomBlock.starts_at < end, RoomBlock.ends_at > start
    ).first()
    return booking is None and block is None

def price_for(room, start, end, unit):
    seconds = (end - start).total_seconds()
    if unit == "hour":
        count = max(1, int((seconds + 3599) // 3600))
        return count * room.hourly_rate_cents
    if unit == "day":
        count = max(1, int((seconds + 86399) // 86400))
        return count * room.daily_rate_cents
    if unit == "week":
        count = max(1, int((seconds + 604799) // 604800))
        return count * room.weekly_rate_cents
    raise ValueError("Choose hour, day or week.")

@rooms_bp.get("/rooms")
def list_rooms():
    rooms = Room.query.order_by(Room.room_number).all()
    now = datetime.utcnow()
    for room in rooms:
        room.currently_available = room_is_available(room.id, now, now + timedelta(minutes=1))
    return render_template("customer/rooms.html", rooms=rooms)

@rooms_bp.get("/rooms/<int:room_id>")
def room_detail(room_id):
    room = db.get_or_404(Room, room_id)
    return render_template("customer/room_detail.html", room=room)

@rooms_bp.get("/rooms/availability")
def availability():
    try:
        room_id = int(request.args.get("room_id", ""))
        start = parse_dt(request.args.get("start", ""))
        end = parse_dt(request.args.get("end", ""))
        if end <= start:
            raise ValueError()
        return jsonify(available=room_is_available(room_id, start, end))
    except (ValueError, TypeError):
        return jsonify(error="Provide a valid room, start and end time."), 400

@rooms_bp.route("/bookings", methods=["GET", "POST"])
@login_required
def bookings():
    if request.method == "POST":
        try:
            room_id = int(request.form.get("room_id", ""))
            start = parse_dt(request.form.get("check_in_at", ""))
            end = parse_dt(request.form.get("check_out_at", ""))
            unit = request.form.get("booking_unit", "")
            room = db.get_or_404(Room, room_id)
            if end <= start or start < datetime.utcnow() - timedelta(minutes=1):
                raise ValueError("Choose a valid future booking period.")
            if not room_is_available(room.id, start, end):
                flash("That room is not available for the selected period.", "danger")
                return redirect(url_for("rooms.list_rooms"))
            total = price_for(room, start, end, unit)
            # Re-check in the same transaction immediately before insert. For multi-worker/high-traffic deployments use PostgreSQL with transactional locking.
            if not room_is_available(room.id, start, end):
                flash("The room was just booked by another customer. Choose another time.", "danger")
                return redirect(url_for("rooms.list_rooms"))
            reference = f"BK-{datetime.utcnow():%y%m%d%H%M%S}-{current_user.id}"
            booking = RoomBooking(booking_reference=reference, room_id=room.id, customer_id=current_user.id,
                                  check_in_at=start, check_out_at=end, booking_unit=unit, total_cents=total,
                                  status="confirmed", payment_status="unpaid")
            db.session.add(booking)
            db.session.flush()
            db.session.add(Notification(user_id=current_user.id, title="Booking confirmed", message=f"Reservation {reference} is confirmed."))
            db.session.add(AuditLog(user_id=current_user.id, action="room_booking_created", entity_type="booking", entity_id=str(booking.id)))
            db.session.commit()
            emit_event("room_availability_changed", {"room_id": room.id, "status": "reserved"})
            flash(f"Booking confirmed. Reference: {reference}. Payment is currently unpaid.", "success")
            return redirect(url_for("rooms.my_bookings"))
        except (ValueError, TypeError):
            db.session.rollback()
            flash("Check the room, dates, times and duration unit.", "danger")
    return render_template("customer/bookings.html", rooms=Room.query.order_by(Room.room_number).all())

@rooms_bp.get("/my-bookings")
@login_required
def my_bookings():
    return render_template("customer/my_bookings.html", bookings=RoomBooking.query.filter_by(customer_id=current_user.id).order_by(RoomBooking.created_at.desc()).all())

@rooms_bp.post("/bookings/<int:booking_id>/cancel")
@login_required
def cancel_booking(booking_id):
    booking = db.get_or_404(RoomBooking, booking_id)
    if current_user.role != "admin" and booking.customer_id != current_user.id:
        abort(403)
    if booking.status != "confirmed" or booking.check_in_at <= datetime.utcnow():
        flash("Only future confirmed bookings can be cancelled here.", "danger")
    else:
        booking.status = "cancelled"
        db.session.add(AuditLog(user_id=current_user.id, action="booking_cancelled", entity_type="booking", entity_id=str(booking.id)))
        db.session.commit()
        emit_event("room_availability_changed", {"room_id": booking.room_id, "status": "available"})
        flash("Booking cancelled. Apply the business refund policy separately if payment was taken.", "success")
    return redirect(url_for("rooms.my_bookings"))

@rooms_bp.post("/staff/bookings/<int:booking_id>/check-in")
@login_required
def check_in(booking_id):
    if current_user.role not in {"admin", "supervisor", "receptionist"}: abort(403)
    booking = db.get_or_404(RoomBooking, booking_id)
    if booking.status != "confirmed" or not room_is_available(booking.room_id, booking.check_in_at, booking.check_out_at):
        flash("Booking cannot be checked in; verify its status and room schedule.", "danger")
    else:
        booking.status = "checked_in"; booking.actual_check_in_at = datetime.utcnow()
        db.session.add(AuditLog(user_id=current_user.id, action="guest_checked_in", entity_type="booking", entity_id=str(booking.id)))
        db.session.commit()
        emit_event("room_availability_changed", {"room_id": booking.room_id, "status": "occupied"})
        flash("Guest checked in.", "success")
    return redirect(request.referrer or url_for("admin.rooms"))

@rooms_bp.post("/staff/bookings/<int:booking_id>/check-out")
@login_required
def check_out(booking_id):
    if current_user.role not in {"admin", "supervisor", "receptionist"}: abort(403)
    booking = db.get_or_404(RoomBooking, booking_id)
    if booking.status != "checked_in":
        flash("Only checked-in bookings can be checked out.", "danger")
    else:
        booking.status = "completed"; booking.actual_check_out_at = datetime.utcnow()
        db.session.add(AuditLog(user_id=current_user.id, action="guest_checked_out", entity_type="booking", entity_id=str(booking.id)))
        db.session.commit()
        emit_event("room_availability_changed", {"room_id": booking.room_id, "status": "available"})
        flash("Guest checked out. Room may require cleaning before reuse.", "success")
    return redirect(request.referrer or url_for("admin.rooms"))
