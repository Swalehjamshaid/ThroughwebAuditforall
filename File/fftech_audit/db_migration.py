
# fftech_audit/db_migration.py
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

def migrate_schedules_table(engine: Engine) -> None:
    insp = inspect(engine)
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

    if statements:
        with engine.begin() as conn:
            for sql in statements:
                conn.execute(text(sql))
