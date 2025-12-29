
# fftech_audit/db_migration.py
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

def migrate_schedules_table(engine: Engine) -> None:
    """
    Add new scheduling columns to 'schedules' table if they don't exist:
      - scheduled_hour   INTEGER DEFAULT 9
      - scheduled_minute INTEGER DEFAULT 0
      - timezone         VARCHAR(64) DEFAULT 'Asia/Karachi'

    Safe to call repeatedly. No-op if columns already exist.
    Works on Postgres and SQLite (SQLite treats VARCHAR as TEXT).
    """
    insp = inspect(engine)

    # If the table doesn't exist yet, create_all() will handle creation in app.py
    try:
        existing_cols = {col["name"] for col in insp.get_columns("schedules")}
    except Exception:
        return

    statements = []
    if "scheduled_hour" not in existing_cols:
        statements.append("ALTER TABLE schedules ADD COLUMN scheduled_hour INTEGER DEFAULT 9")
    if "scheduled_minute" not in existing_cols:
        statements.append("ALTER TABLE schedules ADD COLUMN scheduled_minute INTEGER DEFAULT 0")
    if "timezone" not in existing_cols:
        statements.append("ALTER TABLE schedules ADD COLUMN timezone VARCHAR(64) DEFAULT 'Asia/Karachi'")

    if not statements:
        return

    # Execute each statement inside one transaction
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))
