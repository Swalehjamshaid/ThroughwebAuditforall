
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime
import tempfile, os

def _render_radar_png(category_scores_dict: dict) -> str:
    import matplotlib.pyplot as plt
    import numpy as np
    labels = list(category_scores_dict.keys())
    values = np.array(list(category_scores_dict.values()))
    if not labels:
        labels = ["Performance","SEO","Crawl","Security","Mobile","Intl"]
        values = np.array([0,0,0,0,0,0])
    angles = np.linspace(0, 2*np.pi, len(labels), endpoint=False)
    values_cycle = np.concatenate((values, [values[0]]))
    angles_cycle = np.concatenate((angles, [angles[0]]))
    fig, ax = plt.subplots(figsize=(4.5,4.5), subplot_kw=dict(polar=True))
    ax.plot(angles_cycle, values_cycle, color='#ffc107', linewidth=2)
    ax.fill(angles_cycle, values_cycle, alpha=0.25, color='#ffc107')
    ax.set_xticks(angles); ax.set_xticklabels(labels)
    ax.set_yticks([20,40,60,80,100]); ax.set_ylim(0,100)
    plt.tight_layout()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
    fig.savefig(tmp.name, dpi=200); plt.close(fig)
    return tmp.name

def _as_dict(category_scores):
    if isinstance(category_scores, dict):
        return {k:int(v) for k,v in category_scores.items()}
    try:
        return {it['name']: int(it['score']) for it in category_scores}
    except Exception:
        return {}

def render_pdf(path: str, brand: str, domain: str, grade: str, health_score: int, category_scores, exec_summary: str):
    c = canvas.Canvas(path, pagesize=A4)
    w,h = A4
    c.setFillColor(colors.HexColor('#0B5ED7'))
    c.rect(0, h-60, w, 60, fill=True, stroke=False)
    c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 18)
    c.drawString(20, h-40, f"{brand} · Certified Website Audit")
    c.setFillColor(colors.black)
    c.setFont('Helvetica-Bold', 24); c.drawString(20, h-90, f"Grade: {grade}")
    c.setFont('Helvetica', 12)
    c.drawString(20, h-110, f"Health Score: {health_score}%")
    c.drawString(20, h-126, f"Domain: {domain}")
    c.drawString(20, h-142, f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    c.showPage()
    c.setFont('Helvetica-Bold', 16); c.drawString(20, h-40, 'Executive Summary')
    styles = getSampleStyleSheet(); style = styles['BodyText']; style.leading = 14
    frame = Frame(20, 60, w-40, h-120, showBoundary=0)
    para = Paragraph(exec_summary, style); frame.addFromList([para], c)
    c.showPage()
    c.setFont('Helvetica-Bold', 16); c.drawString(20, h-40, 'Category Comparison (Radar)')
    cat_dict = _as_dict(category_scores)
    radar_png = _render_radar_png(cat_dict)
    c.drawImage(radar_png, 25*mm, h-180, width=120*mm, height=120*mm, preserveAspectRatio=True, mask='auto')
    c.setFont('Helvetica', 10); y = h-200
    for name, score in cat_dict.items():
        c.drawString(20, y-150, f"{name}: {score}"); y -= 12
    c.showPage()
    try: os.remove(radar_png)
    except Exception: pass
    c.setFont('Helvetica-Bold', 16); c.drawString(20, h-40, 'Key Findings & Recommendations')
    c.setFont('Helvetica', 11)
    for ln in ['Optimize LCP/FCP; eliminate render-blocking CSS/JS.', 'Repair broken links; ensure sitemap & canonical consistency.', 'Implement CSP + HSTS; fix mixed content; enforce HTTPS.', 'Improve mobile tap targets & font sizes; check viewport settings.']:
        c.drawString(20, h-70, f"• {ln}"); h -= 16
    c.showPage()
    c.setFont('Helvetica-Bold', 16); c.drawString(20, h-40, 'Category Scores Snapshot')
    c.setFont('Helvetica', 10); y = h-70
    for name, score in cat_dict.items():
        c.drawString(20, y, f"{name}: {score}%"); y -= 12
        if y < 60:
            c.showPage(); c.setFont('Helvetica', 10); y = h-70
    c.setFont('Helvetica', 10); c.setFillColor(colors.HexColor('#0B5ED7'))
    c.drawString(20, 30, f"Certified by {brand} · Valid for 30 days")
    c.showPage(); c.save()
