
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

def migrate_schedules_table(engine: Engine) -> None:
    insp = inspect(engine)
    try:
        cols = {c['name'] for c in insp.get_columns('schedules')}
    except Exception:
        return
    stmts = []
    if 'scheduled_hour' not in cols:
        stmts.append('ALTER TABLE schedules ADD COLUMN scheduled_hour INTEGER DEFAULT 9')
    if 'scheduled_minute' not in cols:
        stmts.append('ALTER TABLE schedules ADD COLUMN scheduled_minute INTEGER DEFAULT 0')
    if 'timezone' not in cols:
        stmts.append("ALTER TABLE schedules ADD COLUMN timezone VARCHAR(64) DEFAULT 'UTC'")
    if 'frequency' not in cols:
        stmts.append("ALTER TABLE schedules ADD COLUMN frequency VARCHAR(20) DEFAULT 'weekly'")
    if stmts:
        with engine.begin() as conn:
            for s in stmts:
                conn.execute(text(s))
