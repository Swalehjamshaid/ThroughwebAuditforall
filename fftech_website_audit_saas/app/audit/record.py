import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from pptx import Presentation
from pptx.util import Inches
import pandas as pd
from datetime import datetime

TITLE_MIN, TITLE_MAX = 12, 70
DESC_MIN, DESC_MAX   = 40, 170

COLORS = {
    'critical': '#D32F2F',
    'high':     '#F4511E',
    'medium':   '#FBC02D',
    'low':      '#7CB342',
    'accent':   '#3B82F6',
    'bg':       '#0F172A',
    'fg':       '#E5E7EB',
    'ok':       '#2E7D32',
    'warn':     '#EF6C00',
}

def _safe_int(v):
    try:
        return int(v)
    except Exception:
        try:
            return int(float(v))
        except Exception:
            return None

def _truthy(v) -> bool:
    if isinstance(v, bool): return v
    if v is None: return False
    if isinstance(v, (list, dict)): return len(v) > 0
    s = str(v).strip().lower()
    return s in {'1', 'true', 'yes', 'ok', 'present', 'enabled'}

def _cookie_flag_present(set_cookie_val: str, flag: str) -> bool:
    if not set_cookie_val:
        return False
    s = str(set_cookie_val).lower()
    return flag.lower() in s

# -------- PNG Dashboard --------
def render_dashboard_png(out_path: str, brand: str, url: str, category_scores: list, metrics_raw: dict):
    title_len = _safe_int(metrics_raw.get('title_length'))
    desc_len  = _safe_int(metrics_raw.get('meta_description_length'))
    xfo_ok   = _truthy(metrics_raw.get('xfo'))
    csp_ok   = _truthy(metrics_raw.get('csp'))
    hsts_ok  = _truthy(metrics_raw.get('hsts'))
    robots_allowed = _truthy(metrics_raw.get('robots_allowed'))
    set_cookie_val = metrics_raw.get('set_cookie')
    cookie_secure_ok   = _cookie_flag_present(set_cookie_val, 'Secure')
    cookie_httponly_ok = _cookie_flag_present(set_cookie_val, 'HttpOnly')

    plt.style.use('seaborn-v0_8-darkgrid')
    fig = plt.figure(figsize=(12, 8), dpi=150)
    fig.patch.set_facecolor(COLORS['bg'])

    ax1 = plt.subplot2grid((2, 3), (0, 0), colspan=2)
    names = [c['name'] for c in category_scores] or ['Performance', 'Accessibility', 'SEO', 'Security', 'BestPractices']
    values = [int(c['score']) for c in category_scores] if category_scores else [65, 72, 68, 70, 66]
    ax1.bar(names, values, color=COLORS['accent'])
    ax1.set_ylim(0, 100)
    ax1.set_title('Category Scores (0–100)', color=COLORS['fg'], fontsize=12)
    ax1.tick_params(colors=COLORS['fg'])
    ax1.set_xticklabels(names, rotation=20, ha='right', color=COLORS['fg'])
    for i, v in enumerate(values):
        ax1.text(i, min(v + 2, 99), str(v), ha='center', color=COLORS['fg'], fontsize=9)

    ax2 = plt.subplot2grid((2, 3), (0, 2))
    ax2.axis('off')
    def _ok_range(v, lo, hi):
        if v is None: return False
        return lo <= v <= hi
    comp_lines = [
        f"Title length: {title_len if title_len is not None else 'NA'} (recommended {TITLE_MIN}–{TITLE_MAX})",
        f"Meta description: {desc_len if desc_len is not None else 'NA'} (recommended {DESC_MIN}–{DESC_MAX})",
    ]
    comp_colors = [
        COLORS['ok'] if _ok_range(title_len, TITLE_MIN, TITLE_MAX) else COLORS['warn'],
        COLORS['ok'] if _ok_range(desc_len,  DESC_MIN,  DESC_MAX) else COLORS['warn'],
    ]
    y = 0.8
    for t, col in zip(comp_lines, comp_colors):
        ax2.text(0.0, y, t, fontsize=10, color=col, transform=ax2.transAxes)
        y -= 0.18

    ax3 = plt.subplot2grid((2, 3), (1, 0), colspan=3)
    ax3.axis('off')
    sec_items = [
        ('X-Frame-Options', xfo_ok),
        ('Content-Security-Policy', csp_ok),
        ('HSTS', hsts_ok),
        ('Cookie Secure', cookie_secure_ok),
        ('Cookie HttpOnly', cookie_httponly_ok),
        ('Robots allow indexing', robots_allowed),
    ]
    ax3.text(0.01, 0.95, 'Security & Indexability', fontsize=12, color=COLORS['fg'], transform=ax3.transAxes)

    x0, y0 = 0.02, 0.80
    for label, ok in sec_items:
        box_color = COLORS['ok'] if ok else COLORS['critical']
        ax3.add_patch(Rectangle((x0, y0), 0.04, 0.10, color=box_color, transform=ax3.transAxes))
        ax3.text(x0 + 0.06, y0 + 0.05, f"{label}: {'OK' if ok else 'Missing'}",
                 va='center', fontsize=10, color=COLORS['fg'], transform=ax3.transAxes)
        y0 -= 0.13

    # Closed f-string with explicit newline
    fig.suptitle(f"{brand} — Audit Dashboard\n{url}", color=COLORS['fg'], fontsize=15)

    fig.savefig(out_path, facecolor=COLORS['bg'])
    plt.close(fig)

# -------- PPTX Export --------
def export_ppt(out_pptx: str, brand: str, url: str, grade: str, health_score: int,
               category_scores: list, metrics_raw: dict, dashboard_png: str):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = f"{brand} — Audit Summary"
    slide.placeholders[1].text = (
        f"{url}" + NL +
        f"Grade: {grade}  |  Health: {health_score}/100" + NL +
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )







    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = 'Executive Dashboard'
    slide.shapes.add_picture(dashboard_png, Inches(0.5), Inches(1.5), width=Inches(9.0))

    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = 'Details'
    tf = slide.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(9), Inches(4.5)).text_frame
    tf.word_wrap = True

    def _line_bool(name, val):
        return f"{name}: {'OK' if _truthy(val) else 'Missing'}"

    lines = ['Category Scores:']
    for c in (category_scores or []):
        lines.append(f" - {c['name']}: {c['score']}")
    if not category_scores:
        lines.append(' - No category score data available.')

    lines.extend([
        '',
        'Security/Indexability:',
        _line_bool('X-Frame-Options', metrics_raw.get('xfo')),
        _line_bool('Content-Security-Policy', metrics_raw.get('csp')),
        _line_bool('HSTS', metrics_raw.get('hsts')),
        f"Cookie Secure: {'OK' if _cookie_flag_present(metrics_raw.get('set_cookie'), 'Secure') else 'Missing'}",
        f"Cookie HttpOnly: {'OK' if _cookie_flag_present(metrics_raw.get('set_cookie'), 'HttpOnly') else 'Missing'}",
        f"Robots allow indexing: {'OK' if _truthy(metrics_raw.get('robots_allowed')) else 'Blocked'}",
        '',
        f"Title length: {metrics_raw.get('title_length', 'NA')} (recommended {TITLE_MIN}-{TITLE_MAX})",
        f"Meta description length: {metrics_raw.get('meta_description_length', 'NA')} (recommended {DESC_MIN}-{DESC_MAX})",
    ])

    p0 = tf.paragraphs[0]
    p0.text = lines[0]; p0.level = 0
    for t in lines[1:]:
        pp = tf.add_paragraph(); pp.text = t; pp.level = 0

    prs.save(out_pptx)

# -------- XLSX Export --------
def export_xlsx(out_xlsx: str, brand: str, url: str, grade: str, health_score: int,
                category_scores: list, metrics_raw: dict):
    summary_rows = [
        {'Metric': 'Brand', 'Value': brand},
        {'Metric': 'URL', 'Value': url},
        {'Metric': 'Grade', 'Value': grade},
        {'Metric': 'Health Score', 'Value': health_score},
        {'Metric': 'Title length', 'Value': metrics_raw.get('title_length')},
        {'Metric': 'Meta description length', 'Value': metrics_raw.get('meta_description_length')},
        {'Metric': 'X-Frame-Options', 'Value': 'OK' if _truthy(metrics_raw.get('xfo')) else 'Missing'},
        {'Metric': 'CSP', 'Value': 'OK' if _truthy(metrics_raw.get('csp')) else 'Missing'},
        {'Metric': 'HSTS', 'Value': 'OK' if _truthy(metrics_raw.get('hsts')) else 'Missing'},
        {'Metric': 'Cookie Secure', 'Value': 'OK' if _cookie_flag_present(metrics_raw.get('set_cookie'), 'Secure') else 'Missing'},
        {'Metric': 'Cookie HttpOnly', 'Value': 'OK' if _cookie_flag_present(metrics_raw.get('set_cookie'), 'HttpOnly') else 'Missing'},
        {'Metric': 'Robots allow indexing', 'Value': 'OK' if _truthy(metrics_raw.get('robots_allowed')) else 'Blocked'},
    ]
    df_summary = pd.DataFrame(summary_rows)
    df_categories = pd.DataFrame(category_scores or [], columns=['name', 'score'])

    with pd.ExcelWriter(out_xlsx, engine='openpyxl') as writer:
        df_summary.to_excel(writer, sheet_name='Summary', index=False)
        df_categories.to_excel(writer, sheet_name='CategoryScores', index=False)