from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_socketio import SocketIO
from flask_migrate import Migrate

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
socketio = SocketIO(async_mode="threading", cors_allowed_origins=[])
migrate = Migrate()


def emit_event(event, data, **kwargs):
    """Broadcast a realtime event when Socket.IO is available."""
    from flask import current_app

    if current_app.config.get("REALTIME_ENABLED", False):
        socketio.emit(event, data, **kwargs)
