from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet
import matplotlib.pyplot as plt
import os
from ..ai.narratives import generate_narrative

plt.switch_backend('Agg')
BRAND_LOGO = 'static/img/logo_fftech.png'


def _chart_bar(scores: dict, out_path: str):
    import matplotlib.pyplot as plt
    plt.figure(figsize=(6,3))
    names=list(scores.keys()); vals=list(scores.values())
    bars=plt.barh(names, vals, color=['#2e86de' if v>=75 else '#e67e22' if v>=60 else '#e74c3c' for v in vals])
    plt.xlim(0,100); plt.xlabel('Score')
    for i,b in enumerate(bars): plt.text(b.get_width()+1, b.get_y()+b.get_height()/3, f"{vals[i]:.1f}")
    plt.tight_layout(); plt.savefig(out_path, dpi=160); plt.close()


def _chart_pie(dist: dict, out_path: str, title: str):
    import matplotlib.pyplot as plt
    plt.figure(figsize=(4,4))
    labels=list(dist.keys()); sizes=list(dist.values());
    if sum(sizes)==0: labels=['N/A']; sizes=[1]
    plt.pie(sizes, labels=labels, autopct='%1.0f%%'); plt.title(title)
    plt.tight_layout(); plt.savefig(out_path, dpi=160); plt.close()


def generate_pdf(pdf_path: str, target_url: str, metrics: dict, scores: dict, overall: float, grade: str):
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    doc = SimpleDocTemplate(pdf_path, pagesize=A4, title='FF Tech Website Audit')
    styles = getSampleStyleSheet(); flow = []
    ai = generate_narrative(target_url, metrics, scores)

    if os.path.exists(BRAND_LOGO): flow.append(Image(BRAND_LOGO, width=140, height=40))
    flow.append(Spacer(1,12))
    flow.append(Paragraph('<b>Executive Summary</b>', styles['Title']))
    flow.append(Paragraph(f'Target: {target_url}', styles['Normal']))
    flow.append(Paragraph(f'Overall Score: <b>{overall:.1f}</b> — Grade: <b>{grade}</b>', styles['Normal']))
    flow.append(Spacer(1,8))
    flow.append(Paragraph(ai.get('summary','Executive narrative unavailable.'), styles['BodyText']))

    cat_chart = os.path.join(os.path.dirname(pdf_path), 'cat_scores.png')
    _chart_bar(scores, cat_chart); flow.append(Spacer(1,8)); flow.append(Image(cat_chart, width=480, height=240))

    table_data = [
        ['Strengths'] + (ai.get('strengths') or []),
        ['Weak Areas'] + (ai.get('weaknesses') or []),
        ['Priority Fixes'] + (ai.get('priorities') or []),
    ]
    t = Table(table_data, style=TableStyle([
        ('BACKGROUND',(0,0),(-1,0), colors.HexColor('#e8f6f3')),
        ('BACKGROUND',(0,1),(-1,1), colors.HexColor('#fdebd0')),
        ('BACKGROUND',(0,2),(-1,2), colors.HexColor('#f5b7b1')),
        ('GRID',(0,0),(-1,-1),0.25,colors.grey)
    ]))
    flow.append(t)
    flow.append(Spacer(1,10))
    flow.append(Paragraph('Conclusion: Execute high-ROI items first to uplift both user experience and search visibility.', styles['Italic']))

    flow.append(Paragraph("", styles['Normal']))
    flow.append(Paragraph('<b>Overall Site Health</b>', styles['Title']))
    health = [['Metric','Value'],
              ['Total Crawled Pages', metrics.get('total_crawled_pages')],
              ['Total Errors', metrics.get('total_errors')],
              ['Total Warnings', metrics.get('total_warnings')],
              ['HTTP 4xx', metrics.get('http_4xx_pages')],
              ['HTTP 5xx', metrics.get('http_5xx_pages')],
              ['Redirect Chains', metrics.get('redirect_chains')]]
    t = Table(health, style=TableStyle([('GRID',(0,0),(-1,-1),0.25,colors.grey), ('BACKGROUND',(0,0),(-1,0),colors.lightgrey)]))
    flow.append(t)
    pie_path = os.path.join(os.path.dirname(pdf_path), 'status_pie.png')
    _chart_pie({'2xx':metrics.get('http_2xx_pages',0),'3xx':metrics.get('http_3xx_pages',0),'4xx':metrics.get('http_4xx_pages',0),'5xx':metrics.get('http_5xx_pages',0)}, pie_path, 'Status Codes')
    flow.append(Image(pie_path, width=320, height=320))
    flow.append(Paragraph('Conclusion: Reduce errors and redirects to stabilize crawl budget.', styles['Italic']))

    flow.append(Paragraph("", styles['Normal']))
    flow.append(Paragraph('<b>Crawlability & On-Page SEO</b>', styles['Title']))
    onp = [['Missing Titles', metrics.get('missing_title_tags')],
           ['Duplicate Titles', metrics.get('duplicate_title_tags')],
           ['Missing Meta', metrics.get('missing_meta_descriptions')],
           ['Missing H1', metrics.get('missing_h1')],
           ['Multiple H1', metrics.get('multiple_h1')],
           ['Missing Image Alts', metrics.get('missing_image_alt_tags')],
           ['Large Images', metrics.get('large_uncompressed_images')],
           ['Low Text/HTML Pages', metrics.get('low_text_to_html_ratio_pages')],
           ['Missing Open Graph', metrics.get('missing_open_graph_tags')]]
    t = Table(onp, style=TableStyle([('GRID',(0,0),(-1,-1),0.25,colors.grey), ('BACKGROUND',(0,0),(-1,0),colors.lightgrey)]))
    flow.append(t)
    flow.append(Paragraph('Conclusion: Fix template-level metadata and compress assets for immediate gains.', styles['Italic']))

    flow.append(Paragraph("", styles['Normal']))
    flow.append(Paragraph('<b>Performance, Mobile & Security</b>', styles['Title']))
    perf = [['Metric','Value'],
            ['LCP (ms)', metrics.get('lcp')],
            ['FCP (ms)', metrics.get('fcp')],
            ['CLS', metrics.get('cls')],
            ['TBT (ms)', metrics.get('total_blocking_time')],
            ['Speed Index (ms)', metrics.get('speed_index')],
            ['TTI (ms)', metrics.get('time_to_interactive')],
            ['HTTPS Implemented', 'Yes' if metrics.get('https_implementation') else 'No']]
    t = Table(perf, style=TableStyle([('GRID',(0,0),(-1,-1),0.25,colors.grey), ('BACKGROUND',(0,0),(-1,0),colors.lightgrey)]))
    flow.append(t)
    flow.append(Paragraph('Conclusion: Use PSI data to prioritize render-blocking fixes and layout stability.', styles['Italic']))

    flow.append(Paragraph("", styles['Normal']))
    flow.append(Paragraph('<b>Opportunities, Growth & ROI</b>', styles['Title']))
    opps = metrics.get('high_impact_opportunities') or ['Maintain stability and monitor monthly trends.']
    odata = [['Recommended Action']] + [[o] for o in opps]
    t = Table(odata, style=TableStyle([('GRID',(0,0),(-1,-1),0.25,colors.grey), ('BACKGROUND',(0,0),(-1,0),colors.lightgrey)]))
    flow.append(t)
    flow.append(Paragraph('Conclusion: Deliver quick wins first, then invest in structural improvements and content expansion.', styles['Italic']))

    doc.build(flow)
    return pdf_path
