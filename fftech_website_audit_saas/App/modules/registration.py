from datetime import datetime

def register_user(conn, name, email, role):
    cur = conn.cursor()
    cur.execute('INSERT INTO users (name, email, role, created_at) VALUES (?, ?, ?, ?)',
                (name, email, role, datetime.utcnow().isoformat()))
    conn.commit()

def get_users(conn):
    conn.row_factory = _dict_factory
    cur = conn.cursor()
    cur.execute('SELECT id, name, email, role, created_at FROM users ORDER BY id DESC')
    return cur.fetchall()

def _dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d
