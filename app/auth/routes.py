from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from sqlalchemy import func
from urllib.parse import urlsplit
from ..extensions import db
from ..models import User, AuditLog

auth_bp = Blueprint("auth", __name__)

def _safe_next(target):
    """Only allow same-site relative redirects after login."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        return None
    return target

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not name or not email or len(name) > 120:
            flash("Enter your name and a valid email address.", "danger")
        elif len(password) < 10:
            flash("Use a password with at least 10 characters.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        elif User.query.filter(func.lower(User.email) == email).first():
            flash("An account with that email already exists.", "danger")
        else:
            user = User(full_name=name, email=email, phone=phone, role="customer")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Account created. You can now sign in.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/register.html")

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter(func.lower(User.email) == email).first()
        if not user or not user.check_password(password) or not user.is_active_account:
            flash("Invalid email or password, or the account is inactive.", "danger")
        else:
            login_user(user, remember=bool(request.form.get("remember")))
            db.session.add(AuditLog(user_id=user.id, action="login", entity_type="user", entity_id=str(user.id)))
            db.session.commit()
            return redirect(_safe_next(request.args.get("next")) or url_for("main.dashboard"))
    return render_template("auth/login.html")

@auth_bp.post("/logout")
def logout():
    if current_user.is_authenticated:
        db.session.add(AuditLog(user_id=current_user.id, action="logout", entity_type="user", entity_id=str(current_user.id)))
        db.session.commit()
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("main.index"))
