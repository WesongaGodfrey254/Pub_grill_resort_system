from io import BytesIO
from flask import Blueprint, render_template, redirect, url_for, abort, send_file
from flask_login import current_user
from sqlalchemy import func, text
from ..models import Category, Product, Order, Room, RoomBooking, User, UploadedFile
from ..extensions import db
from datetime import datetime

main_bp = Blueprint("main", __name__)

@main_bp.get("/healthz")
def healthz():
    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        db.session.rollback()
        return {"status": "unavailable"}, 503

@main_bp.get("/uploads/<folder>/<filename>")
def uploaded_file(folder, filename):
    record = UploadedFile.query.filter_by(folder=folder, filename=filename).first()
    if record is None:
        abort(404)
    response = send_file(
        BytesIO(record.data),
        mimetype=record.mimetype,
        download_name=record.filename,
        max_age=31536000,
        conditional=True,
    )
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response

@main_bp.route("/")
def index():
    categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
    products = Product.query.filter_by(is_available=True).order_by(Product.name).limit(12).all()
    rooms = Room.query.filter_by(status="available").order_by(Room.room_number).limit(6).all()
    return render_template("index.html", categories=categories, products=products, rooms=rooms)

@main_bp.route("/dashboard")
def dashboard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    if current_user.role == "admin" or current_user.role == "supervisor":
        return redirect(url_for("admin.dashboard"))
    if current_user.role in {"chef", "bartender", "waiter", "cashier", "receptionist", "storekeeper"}:
        return redirect(url_for("admin.operations"))
    return render_template("customer/dashboard.html",
        orders=Order.query.filter_by(customer_id=current_user.id).order_by(Order.created_at.desc()).limit(10).all(),
        bookings=RoomBooking.query.filter_by(customer_id=current_user.id).order_by(RoomBooking.created_at.desc()).limit(10).all())
