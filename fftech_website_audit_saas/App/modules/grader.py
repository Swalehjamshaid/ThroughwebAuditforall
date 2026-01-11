from collections import Counter

def compute_metrics(conn, audit_id):
    conn.row_factory = _dict_factory
    cur = conn.cursor()
    cur.execute('SELECT weight, score, status FROM audit_items WHERE audit_id = ?', (audit_id,))
    rows = cur.fetchall()
    total_items = len(rows)
    if total_items == 0:
        return {
            'total_items': 0,
            'completed_items': 0,
            'avg_score': 0.0,
            'compliance_rate': 0.0,
            'weighted_score': 0.0
        }
    completed_items = sum(1 for r in rows if r['status'] == 'completed')
    avg_score = sum(r['score'] for r in rows) / total_items
    weight_sum = sum(r['weight'] for r in rows)
    weighted_score = (sum(r['weight'] * r['score'] for r in rows) / weight_sum) if weight_sum else 0.0
    status_counts = Counter(r['status'] for r in rows)
    compliance_rate = (completed_items / total_items) * 100

    return {
        'total_items': total_items,
        'completed_items': completed_items,
        'avg_score': round(avg_score, 2),
        'weighted_score': round(weighted_score, 2),
        'compliance_rate': round(compliance_rate, 2),
        'status_counts': dict(status_counts)
    }

def _dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d
