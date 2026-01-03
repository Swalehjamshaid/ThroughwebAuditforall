
import requests
from urllib.parse import urlparse
from typing import Dict, List

# Placeholder: real implementation would be extensive and may call PSI/Lighthouse and parse HTML deeply.

def run_basic_checks(url: str) -> Dict:
    metrics = []
    top_issues = []

    # HTTP status
    try:
        r = requests.get(url, timeout=20)
        status = r.status_code
        if 200 <= status < 300:
            metrics.append({'name':'HTTP Status Codes','status':'good','details':f'{status}'})
        elif 300 <= status < 400:
            metrics.append({'name':'HTTP Status Codes','status':'warn','details':f'{status} redirect'})
            top_issues.append('Excessive redirects')
        else:
            metrics.append({'name':'HTTP Status Codes','status':'bad','details':f'{status}'})
            top_issues.append('Non-2xx response')
    except Exception as e:
        metrics.append({'name':'HTTP Status Codes','status':'bad','details':str(e)})
        top_issues.append('Site unreachable')

    # HTTPS check
    parsed = urlparse(url)
    if parsed.scheme == 'https':
        metrics.append({'name':'HTTPS Implemented','status':'good','details':'HTTPS in use'})
    else:
        metrics.append({'name':'HTTPS Implemented','status':'bad','details':'Not using HTTPS'})
        top_issues.append('HTTPS not enforced')

    # Basic meta checks
    try:
        html = r.text if 'r' in locals() else ''
        has_title = '<title>' in html.lower()
        metrics.append({'name':'Missing Title Tags','status':'good' if has_title else 'bad','details':'Title present' if has_title else 'Missing <title>'})
        has_meta_desc = '<meta name="description"' in html.lower()
        metrics.append({'name':'Missing Meta Descriptions','status':'good' if has_meta_desc else 'warn','details':'Meta description present' if has_meta_desc else 'No meta description'})
    except Exception:
        pass

    # Very naive scoring
    good = sum(1 for m in metrics if m['status']=='good')
    warn = sum(1 for m in metrics if m['status']=='warn')
    bad = sum(1 for m in metrics if m['status']=='bad')
    health_score = max(0, min(100, int(100 * (good*1 + warn*0.6) / max(1,(good+warn+bad)) )))

    # Category scores (placeholder)
    category_scores = {
        'Overall Site Health': health_score,
        'Crawlability & Indexation': health_score - 5 if health_score>5 else health_score,
        'On-Page SEO': health_score - 10 if health_score>10 else health_score,
        'Technical & Performance': health_score - 15 if health_score>15 else health_score,
        'Mobile & Usability': health_score - 10 if health_score>10 else health_score,
        'Security & HTTPS': 100 if parsed.scheme=='https' else 20,
        'International SEO': 50,
        'Backlinks & Authority': 50,
        'Advanced/Thematic': 50,
        'Trend/Historical': 50,
    }

    return {
        'metrics': metrics,
        'category_scores': category_scores,
        'top_issues': top_issues,
        'health_score': health_score
    }
