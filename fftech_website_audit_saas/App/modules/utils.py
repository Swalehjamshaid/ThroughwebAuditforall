import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def generate_charts(conn, audit_id, output_dir):
    conn.row_factory = _dict_factory
    cur = conn.cursor()
    cur.execute('SELECT item, score, status FROM audit_items WHERE audit_id = ? ORDER BY id', (audit_id,))
    rows = cur.fetchall()

    chart_paths = {}
    os.makedirs(output_dir, exist_ok=True)

    if not rows:
        return chart_paths

    items = [r['item'] for r in rows]
    scores = [r['score'] for r in rows]
    plt.figure(figsize=(10, 4))
    plt.bar(items, scores, color='#2a6f97')
    plt.xticks(rotation=45, ha='right')
    plt.ylabel('Score')
    plt.title('Audit Item Scores')
    bar_path = os.path.join(output_dir, f'audit_{audit_id}_bar.png')
    plt.tight_layout()
    plt.savefig(bar_path)
    plt.close()
    chart_paths['bar'] = os.path.basename(bar_path)

    status_labels = {}
    for r in rows:
        status_labels[r['status']] = status_labels.get(r['status'], 0) + 1
    labels = list(status_labels.keys())
    sizes = list(status_labels.values())
    colors = ['#1f7a8c', '#bfd7ea', '#022b3a', '#e1e5f2']
    plt.figure(figsize=(4, 4))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', colors=colors[:len(labels)])
    plt.title('Status Distribution')
    pie_path = os.path.join(output_dir, f'audit_{audit_id}_pie.png')
    plt.tight_layout()
    plt.savefig(pie_path)
    plt.close()
    chart_paths['pie'] = os.path.basename(pie_path)

    cum = []
    s = 0.0
    for i, val in enumerate(scores, start=1):
        s += val
        cum.append(s / i)
    plt.figure(figsize=(8, 3))
    plt.plot(range(1, len(cum)+1), cum, marker='o', color='#014f86')
    plt.xlabel('Item sequence')
    plt.ylabel('Cumulative average')
    plt.title('Cumulative Average Score')
    line_path = os.path.join(output_dir, f'audit_{audit_id}_line.png')
    plt.tight_layout()
    plt.savefig(line_path)
    plt.close()
    chart_paths['line'] = os.path.basename(line_path)

    return chart_paths


def _dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d
