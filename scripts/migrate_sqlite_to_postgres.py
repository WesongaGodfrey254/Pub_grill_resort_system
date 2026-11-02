"""Copy an existing SQLite database into the configured PostgreSQL database.

Run this once after switching ``DATABASE_URL`` to PostgreSQL:

    python scripts/migrate_sqlite_to_postgres.py

The script is safe to re-run: target tables are cleared and repopulated from the
SQLite source. ``business_profile`` is left untouched because it is new.
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import Boolean, DateTime, text

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402

# Parents before children so PostgreSQL foreign keys stay valid.
TABLE_ORDER = [
    "user",
    "category",
    "product",
    "restaurant_table",
    "order",
    "order_item",
    "order_status_history",
    "room",
    "room_booking",
    "room_block",
    "payment",
    "inventory_movement",
    "notification",
    "discount",
    "audit_log",
]


def _convert(value, column):
    if value is None:
        return None
    if isinstance(column.type, Boolean):
        return bool(value)
    if isinstance(column.type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def migrate(source_path):
    app = create_app()
    with app.app_context():
        engine = db.engine
        source = sqlite3.connect(source_path)
        source.row_factory = sqlite3.Row
        metadata = db.metadata

        with engine.begin() as connection:
            for table_name in reversed(TABLE_ORDER):
                connection.execute(text(f'DELETE FROM "{table_name}"'))

            for table_name in TABLE_ORDER:
                table = metadata.tables.get(table_name)
                if table is None:
                    continue
                source_columns = {
                    row["name"] for row in source.execute(f'PRAGMA table_info("{table_name}")')
                }
                columns = [column for column in table.columns if column.name in source_columns]
                if not columns:
                    continue
                selected = ", ".join(f'"{column.name}"' for column in columns)
                rows = source.execute(f'SELECT {selected} FROM "{table_name}"').fetchall()
                if not rows:
                    continue
                payload = [
                    {column.name: _convert(row[column.name], column) for column in columns}
                    for row in rows
                ]
                connection.execute(table.insert(), payload)
                if any(column.name == "id" for column in columns):
                    connection.execute(text(
                        f'SELECT setval(pg_get_serial_sequence(\'public."{table_name}"\', \'id\'), '
                        f'COALESCE((SELECT MAX(id) FROM "{table_name}"), 1), true)'
                    ))
                print(f"Copied {len(payload)} row(s) into {table_name}.")

        source.close()
        print("SQLite data copied to PostgreSQL successfully.")


if __name__ == "__main__":
    default_source = BASE_DIR / "instance" / "pub_grill.db"
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else default_source
    if not source.is_file():
        raise SystemExit(f"SQLite database not found: {source}")
    migrate(source)
