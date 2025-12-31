# fftech_audit/db_migration.py
from fftech_audit.db import init_db

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
