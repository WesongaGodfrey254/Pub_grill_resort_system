# Pub, Grill, Restaurant & Room Booking Management System

A Flask + SQLite starter implementation with customer accounts, role-based staff/admin access, dynamic menus, orders, Socket.IO updates, inventory tracking, room booking, booking conflict checks, and operational reporting.

## Features implemented
- Customer registration and login; secure password hashes; session login.
- Role-aware admin, supervisor, employee and customer views.
- Dynamic categories and products with editable prices and stock.
- Cart in browser storage and server-side price/stock validation.
- Order creation, order history, status history and Socket.IO broadcasts.
- Staff order dashboard, employee account management and audit logs.
- Rooms with hourly/daily/weekly rates, reservation overlap checks, maintenance blocks, cancellations, check-in/out.
- Basic sales/status reports, low-stock indicators and notifications.
- CSRF protection on forms, ORM queries, environment-based secret configuration.
- SQLite database and migration-ready Flask-Migrate setup.

## Requirements
Python 3.10+ recommended. Test on your chosen Python version before production.

## Install on Kali Linux
```bash
cd pub_grill_management
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`. Replace `SECRET_KEY` with a random secret and set a unique bootstrap administrator email and strong password. Never commit `.env`.

Generate a secret:
```bash
python -c 'import secrets; print(secrets.token_hex(32))'
```

Start locally:
```bash
python run.py
```
Open http://127.0.0.1:5000

The administrator login is driven by `.env`. On startup the account matching `BOOTSTRAP_ADMIN_EMAIL` is created if missing (even when other administrators exist), promoted to an active admin, and its password is reset to `BOOTSTRAP_ADMIN_PASSWORD` if it no longer matches. Editing those variables and restarting is therefore enough to control or recover admin access. After first setup, blank or remove the bootstrap variables so in-app password changes are not overwritten. The example values are placeholders and must not be used on a public server.

## Important implementation notes
- Currency is displayed as KES; prices are stored as integer cents (100 units per KES for this starter).
- Timestamps in this initial build are stored as naive UTC. The room date-time inputs currently need to be supplied consistently with that convention. For production, convert input/output using `zoneinfo.ZoneInfo("Africa/Nairobi")` and store UTC-aware timestamps.
- SQLite is appropriate for local/small installations. High-concurrency booking deployments should use PostgreSQL and transactional locking/constraints to prevent races across workers.
- Payment options are recorded in the database, but this build does not claim to process M-Pesa/card payments automatically. Integrate a payment provider and verify signed/server-side callbacks before marking payment as paid.
- Automatic room availability is computed from reservation overlap and maintenance blocks. A room marked available does not override a conflicting reservation.
- Add automated tests, HTTPS, production Socket.IO configuration, rate limiting, backups, email verification and password-reset delivery before production use.
- Alcohol sales must follow applicable legal age requirements and business policies.
