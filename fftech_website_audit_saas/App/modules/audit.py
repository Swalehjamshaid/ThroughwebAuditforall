from datetime import datetime

def get_audits(conn):
    conn.row_factory = _dict_factory
    cur = conn.cursor()
    cur.execute('SELECT id, title, category, date, created_by FROM audits ORDER BY date DESC, id DESC')
    return cur.fetchall()

def get_audit_by_id(conn, audit_id):
    conn.row_factory = _dict_factory
    cur = conn.cursor()
    cur.execute('SELECT id, title, category, date, created_by FROM audits WHERE id = ?', (audit_id,))
    return cur.fetchone()

def create_audit(conn, title, category, created_by):
    cur = conn.cursor()
    cur.execute('INSERT INTO audits (title, category, date, created_by) VALUES (?, ?, DATE("now"), ?)',
                (title, category, created_by))
    conn.commit()
    return cur.lastrowid

def add_audit_item(conn, audit_id, item, weight, score, status):
    cur = conn.cursor()
    cur.execute(INSERT INTO audit_items (audit_id, item, weight, score, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?),
                (audit_id, item, weight, score, status, datetime.utcnow().isoformat()))
    conn.commit()

def get_items_for_audit(conn, audit_id):
    conn.row_factory = _dict_factory
    cur = conn.cursor()
    cur.execute('SELECT id, item, weight, score, status, created_at FROM audit_items WHERE audit_id = ? ORDER BY id DESC',
                (audit_id,))
    return cur.fetchall()

def _dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
        
    return d
