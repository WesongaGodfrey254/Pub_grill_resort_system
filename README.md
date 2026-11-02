# Pub, Grill, Restaurant & Room Booking Management System

A Flask + PostgreSQL management system with customer accounts, role-based staff/admin access, dynamic menus, product pictures, business branding, orders, Socket.IO updates, inventory tracking, room booking, booking conflict checks, and operational reporting.

## Features implemented
- Customer registration and login; secure password hashes; session login.
- Role-aware admin, supervisor, employee and customer views.
- Dynamic categories and products with editable prices and stock.
- Admin business profile: change the business name and upload/replace the profile picture used in the site header, page titles and footer.
- Product pictures uploaded by the administrator, shown on the menu, home page and product manager.
- Cart in browser storage and server-side price/stock validation.
- Order creation, order history, status history and Socket.IO broadcasts.
- Staff order dashboard, employee account management and audit logs.
- Rooms with hourly/daily/weekly rates, reservation overlap checks, maintenance blocks, cancellations, check-in/out.
- Basic sales/status reports, low-stock indicators and notifications.
- CSRF protection on forms, ORM queries, environment-based secret configuration.
- PostgreSQL database (via `psycopg`) with migration-ready Flask-Migrate setup.

## Requirements
- Python 3.10+ recommended. Test on your chosen Python version before production.
- PostgreSQL 14+ (a `docker-compose.yml` is included for a local database).

## Install
```bash
cd pub_grill_management
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Start PostgreSQL
The simplest local setup uses Docker:
```bash
docker compose up -d
```
This starts PostgreSQL using the credentials in `.env.example` (`pub_grill` / `pub_grill` / database `pub_grill`) on port 5432. If port 5432 is already in use, run `POSTGRES_PORT=5433 docker compose up -d` and update `DATABASE_URL` in `.env` to the same port.

If you already run PostgreSQL, create a database and user and point `DATABASE_URL` at them, for example:
```text
DATABASE_URL=postgresql+psycopg://pub_grill:pub_grill@localhost:5432/pub_grill
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

## Administrator login
The administrator login is driven by `.env`. On startup the account matching `BOOTSTRAP_ADMIN_EMAIL` is created if missing (even when other administrators exist), promoted to an active admin, and its password is reset to `BOOTSTRAP_ADMIN_PASSWORD` if it no longer matches. Editing those variables and restarting is therefore enough to control or recover admin access. After first setup, blank or remove the bootstrap variables so in-app password changes are not overwritten. The example values are placeholders and must not be used on a public server.

## Business profile and product pictures
Sign in as an administrator, open **Dashboard → Business profile**, and change the business name or upload/replace the profile picture. The new name and picture appear on public pages immediately.

On **Products**, the administrator can attach a picture while adding an item and can replace a product picture later. Supported formats are PNG, JPG/JPEG, GIF and WEBP up to 5 MB. Uploaded files are validated and stored under `app/static/uploads/business` and `app/static/uploads/products`; these folders are excluded from git.

## Moving existing SQLite data
Earlier versions used SQLite. To copy that data into PostgreSQL after setting `DATABASE_URL`, run:
```bash
python scripts/migrate_sqlite_to_postgres.py
```
The script reads `instance/pub_grill.db` by default, clears the matching PostgreSQL tables and copies users, categories, products, rooms, bookings, orders and audit history.

## Important implementation notes
- Currency is displayed as KES; prices are stored as integer cents (100 units per KES for this starter).
- Timestamps in this initial build are stored as naive UTC. The room date-time inputs currently need to be supplied consistently with that convention. For production, convert input/output using `zoneinfo.ZoneInfo("Africa/Nairobi")` and store UTC-aware timestamps.
- PostgreSQL is the supported database. Use transactional locking/constraints for high-concurrency booking deployments to prevent races across workers.
- Payment options are recorded in the database, but this build does not claim to process M-Pesa/card payments automatically. Integrate a payment provider and verify signed/server-side callbacks before marking payment as paid.
- Automatic room availability is computed from reservation overlap and maintenance blocks. A room marked available does not override a conflicting reservation.
- Add automated tests, HTTPS, production Socket.IO configuration, rate limiting, backups, email verification and password-reset delivery before production use.
- Alcohol sales must follow applicable legal age requirements and business policies.
