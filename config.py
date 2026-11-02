import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.pool import NullPool

BASE_DIR = Path(__file__).resolve().parent

# Load .env for every entry point (python run.py, flask run, gunicorn, tests).
# Existing environment variables keep precedence.
load_dotenv(BASE_DIR / ".env")

# Vercel (and other serverless hosts) must use an external database and do not
# support long-lived Socket.IO connections or a writable project directory.
IS_SERVERLESS = bool(os.environ.get("VERCEL")) or os.environ.get("SERVERLESS") == "1"


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _database_url():
    """Return a PostgreSQL SQLAlchemy URL, normalising common provider formats."""
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        return "postgresql+psycopg://pub_grill:pub_grill@localhost:5432/pub_grill"
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _trusted_hosts():
    hosts = (os.environ.get("TRUSTED_HOSTS") or "").strip()
    if not hosts:
        return None
    return [host.strip() for host in hosts.split(",") if host.strip()]


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or (
        "" if IS_SERVERLESS else "dev-only-change-this-key"
    )
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 2,
        "max_overflow": 3,
    }
    if IS_SERVERLESS:
        # Vercel functions are short-lived; avoid keeping idle Neon connections
        # and disable psycopg prepared statements for the PgBouncer pooler.
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
            "pool_recycle": 300,
            "poolclass": NullPool,
            "connect_args": {"prepare_threshold": None},
        }

    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = True if IS_SERVERLESS else _env_bool("COOKIE_SECURE", default=False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = True if IS_SERVERLESS else _env_bool("COOKIE_SECURE", default=False)
    REMEMBER_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12
    PREFERRED_URL_SCHEME = "https" if IS_SERVERLESS else "http"
    TRUSTED_HOSTS = _trusted_hosts()
    REALTIME_ENABLED = False if IS_SERVERLESS else _env_bool("REALTIME_ENABLED", default=True)
    AUTO_CREATE_TABLES = _env_bool("AUTO_CREATE_TABLES", default=True)

    BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "The Pub & Grill")
    CURRENCY = os.environ.get("CURRENCY", "KES")
    TIMEZONE = os.environ.get("TIMEZONE", "Africa/Nairobi")
