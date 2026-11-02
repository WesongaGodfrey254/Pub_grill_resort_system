import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Load .env for every entry point (python run.py, flask run, gunicorn, tests).
# Existing environment variables keep precedence.
load_dotenv(BASE_DIR / ".env")

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

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-this-key")
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
    BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "The Pub & Grill")
    CURRENCY = os.environ.get("CURRENCY", "KES")
    TIMEZONE = os.environ.get("TIMEZONE", "Africa/Nairobi")
