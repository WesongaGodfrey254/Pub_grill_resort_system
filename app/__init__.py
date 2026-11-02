import os
import secrets
from pathlib import Path
from datetime import datetime, timezone
from flask import Flask, g, render_template, request, url_for
from flask_login import current_user
from werkzeug.middleware.proxy_fix import ProxyFix
from .extensions import db, login_manager, csrf, socketio, migrate
from config import Config

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY must be configured in the production environment.")
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("DATABASE_URL must point to a PostgreSQL database in production.")

    # Vercel terminates TLS in front of the function, so trust its proxy headers
    # to generate https:// URLs and mark sessions as secure.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_port=1, x_prefix=1)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"
    csrf.init_app(app)

    # Serverless functions cannot keep a Socket.IO connection alive. Realtime
    # updates can be re-enabled with REALTIME_ENABLED=true on a long-running host.
    if app.config.get("REALTIME_ENABLED"):
        socketio.init_app(app, cors_allowed_origins=[])

        @socketio.on("connect")
        def socket_connect(auth=None):
            # Socket rooms are server-assigned; clients cannot choose another user's room.
            if not current_user.is_authenticated:
                return False
            from flask_socketio import join_room
            join_room(f"user:{current_user.id}")
            if current_user.role in {"admin", "supervisor", "chef", "bartender", "waiter", "cashier"}:
                join_room("staff")
            if current_user.role in {"admin", "supervisor"}:
                join_room("management")

    migrate.init_app(app, db)

    @app.before_request
    def add_csp_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.after_request
    def add_security_headers(response):
        nonce = g.get("csp_nonce", "")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "base-uri 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "img-src 'self' data:; "
            "font-src 'self' https://fonts.gstatic.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            f"script-src 'self' 'nonce-{nonce}' https://cdn.socket.io; "
            "connect-src 'self' ws: wss:;",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if app.config.get("SESSION_COOKIE_SECURE") or request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload"
            )
        return response

    from . import models  # noqa: F401
    from .auth.routes import auth_bp
    from .main.routes import main_bp
    from .admin.routes import admin_bp
    from .orders.routes import orders_bp
    from .rooms.routes import rooms_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(rooms_bp)

    @app.context_processor
    def inject_globals():
        from .models import BusinessProfile
        profile = db.session.get(BusinessProfile, 1)
        business_name = profile.name if profile and profile.name else app.config["BUSINESS_NAME"]

        def media_url(path):
            parts = (path or "").split("/")
            if len(parts) == 3 and parts[0] == "uploads" and parts[1] and parts[2]:
                return url_for("main.uploaded_file", folder=parts[1], filename=parts[2])
            return ""

        return {
            "business_name": business_name,
            "business_logo": profile.logo_path if profile else None,
            "currency": app.config["CURRENCY"],
            "csp_nonce": g.get("csp_nonce", ""),
            "realtime_enabled": app.config.get("REALTIME_ENABLED", False),
            "media_url": media_url,
        }

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    with app.app_context():
        if app.config.get("AUTO_CREATE_TABLES", True):
            db.create_all()
        _bootstrap_admin(app)
        _seed_categories()
        _bootstrap_business_profile(app)

    return app

def _bootstrap_admin(app):
    from sqlalchemy import func
    from .models import User, AuditLog

    email = (os.environ.get("BOOTSTRAP_ADMIN_EMAIL") or "").strip().lower()
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD") or ""
    name = (os.environ.get("BOOTSTRAP_ADMIN_NAME") or "System Administrator").strip()
    if not email or not password:
        return
    if len(password) < 12:
        app.logger.warning(
            "Bootstrap admin password is shorter than 12 characters; using it anyway because .env is authoritative."
        )

    user = User.query.filter(func.lower(User.email) == email).first()
    created = False
    if user is None:
        # .env is authoritative: create the configured admin even if other
        # administrators already exist, so editing .env always gives a login.
        user = User(full_name=name, email=email, role="admin", is_active_account=True)
        db.session.add(user)
        created = True

    changed = created
    if user.full_name != name:
        user.full_name = name
        changed = True
    if user.role != "admin":
        user.role = "admin"
        changed = True
    if not user.is_active_account:
        user.is_active_account = True
        changed = True
    # The bootstrap credentials stay authoritative while they remain configured,
    # so editing .env is enough to recover access. Blank them after setup.
    if created or not user.check_password(password):
        user.set_password(password)
        changed = True
    if not changed:
        return

    db.session.flush()
    db.session.add(AuditLog(
        user_id=user.id,
        action="bootstrap_admin_created" if created else "bootstrap_admin_synced",
        entity_type="user",
        entity_id=str(user.id),
    ))
    db.session.commit()
    app.logger.info("%s bootstrap administrator %s.", "Created" if created else "Synchronized", email)

def _bootstrap_business_profile(app):
    from .models import BusinessProfile
    if db.session.get(BusinessProfile, 1) is None:
        db.session.add(BusinessProfile(id=1, name=app.config["BUSINESS_NAME"]))
        db.session.commit()

def _seed_categories():
    from .models import Category
    defaults = ["Soft Drinks", "Alcoholic Drinks", "Grilled Food", "Main Meals", "Snacks", "Desserts", "Non-Alcoholic Cocktails"]
    for name in defaults:
        if not Category.query.filter_by(name=name).first():
            db.session.add(Category(name=name, description=f"{name} menu category"))
    db.session.commit()
