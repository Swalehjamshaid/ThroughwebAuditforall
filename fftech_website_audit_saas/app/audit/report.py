from weasyprint import HTML
from io import BytesIO
from jinja2 import Environment, FileSystemLoader
import matplotlib.pyplot as plt
import base64

env = Environment(loader=FileSystemLoader('app/templates'))

def build_pdf(payload: Dict, overall: float, cat_scores: Dict, url: str) -> bytes:
    # Generate category chart (bar chart)
    fig, ax = plt.subplots(figsize=(10, 6))
    categories = list(cat_scores.keys())
    scores = list(cat_scores.values())
    ax.barh(categories, scores, color='royalblue')
    ax.set_xlim(0, 100)
    ax.set_xlabel('Score (%)')
    ax.set_title('Category Performance Breakdown')
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    chart_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()

    # Render multi-page HTML template
    template = env.get_template('report.html')
    html_content = template.render(
        url=url,
        overall=round(overall, 1),
        grade=grade_from_score(overall),
        cat_scores=cat_scores,
        chart_img=f"data:image/png;base64,{chart_base64}",
        strengths=["Strong HTTPS", "Good crawlability"],
        weaknesses=["Missing meta descriptions", "Some broken links"],
        priorities=["Add alt tags to images", "Fix 4xx errors"],
        date="January 15, 2026",
        brand="FF Tech"
    )

    # Generate PDF
    pdf_bytes = BytesIO()
    HTML(string=html_content).write_pdf(pdf_bytes)
    pdf_bytes.seek(0)
    return pdf_bytes.getvalue()
