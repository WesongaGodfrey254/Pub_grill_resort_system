"""WSGI entry point used by Vercel, gunicorn, uWSGI and other servers.

Locally run the development server with ``python run.py``. In production the
app is served with ``gunicorn wsgi:app`` or Vercel's Python service runtime.
"""

from app import create_app

app = create_app()
application = app
