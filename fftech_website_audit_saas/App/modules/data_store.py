import sqlite3
from datetime import datetime

DB_PATH = 'audit_portal.db'

SCHEMA = [
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        role TEXT,
        created_at TEXT NOT NULL
    ),
    CREATE TABLE IF NOT EXISTS audits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT,
        date TEXT NOT NULL,
        created_by TEXT
    ),
    CREATE TABLE IF NOT EXISTS audit_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        audit_id INTEGER NOT NULL,
        item TEXT NOT NULL,
        weight REAL NOT NULL,
        score REAL NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(audit_id) REFERENCES audits(id) ON DELETE CASCADE
    )
]

SEED_USERS = [
    ('Lead Auditor', 'auditor@example.com', 'auditor'),
    ('Operations Manager', 'ops@example.com', 'manager'),
]

SEED_AUDITS = [
    ('Health & Safety Q1', 'Safety', 'Admin'),
    ('Process Compliance Jan', 'Compliance', 'QA Team'),
]

SEED_ITEMS = {
    1: [
        ('PPE availability', 1.0, 85, 'completed'),
        ('Fire exits clear', 1.0, 95, 'completed'),
        ('First-aid stocked', 1.0, 70, 'in-progress'),
    ],
    2: [
        ('SOP alignment', 1.5, 88, 'completed'),
        ('Checklist usage', 1.0, 76, 'completed'),
        ('Training logs', 1.2, 60, 'pending'),
    ]
}

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db(conn):
    cur = conn.cursor()
    for ddl in SCHEMA:
        cur.execute(eval(ddl))
    conn.commit()

    cur.execute('SELECT COUNT(*) FROM users')
    if cur.fetchone()[0] == 0:
        for name, email, role in SEED_USERS:
            cur.execute('INSERT INTO users (name, email, role, created_at) VALUES (?, ?, ?, ?)',
                        (name, email, role, datetime.utcnow().isoformat()))
    cur.execute('SELECT COUNT(*) FROM audits')
    if cur.fetchone()[0] == 0:
        for title, category, creator in SEED_AUDITS:
            cur.execute('INSERT INTO audits (title, category, date, created_by) VALUES (?, ?, ?, ?)',
                        (title, category, datetime.utcnow().date().isoformat(), creator))
        conn.commit()
        cur.execute('SELECT id FROM audits ORDER BY id')
        audit_ids = [row[0] for row in cur.fetchall()]
        for idx, audit_id in enumerate(audit_ids, start=1):
            items = SEED_ITEMS.get(idx, [])
            for item, weight, score, status in items:
                cur.execute(INSERT INTO audit_items (audit_id, item, weight, score, status, created_at)
                               VALUES (?, ?, ?, ?, ?, ?),
                            (audit_id, item, weight, score, status, datetime.utcnow().isoformat()))
    conn.commit()
