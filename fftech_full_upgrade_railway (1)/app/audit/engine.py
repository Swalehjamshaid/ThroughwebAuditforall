
import os
import requests
from urllib.parse import urlparse
from typing import Dict, List, Tuple

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
GOOGLE_PSI_API_KEY = os.getenv("GOOGLE_PSI_API_KEY", "")

def _status_to_flag(status: int) -> Tuple[str, List[str]]:
    top_issues = []
    if 200 <= status < 300:
        return ('good', top_issues)
    if 300 <= status < 400:
        top_issues.append('Excessive redirects')
        return ('warn', top_issues)
    top_issues.append('Non-2xx response')
    return ('bad', top_issues)

def _run_psi(url: str, strategy: str = 'mobile') -> Dict:
    if not GOOGLE_PSI_API_KEY:
        return {}
    params = {'url': url, 'key': GOOGLE_PSI_API_KEY, 'strategy': strategy, 'category': 'performance'}
    try:
        r = requests.get(PSI_ENDPOINT, params=params, timeout=60)
        r.raise_for_status(); return r.json()
    except Exception:
        return {}

def run_basic_checks(url: str) -> Dict:
    metrics: List[Dict] = []
    top_issues: List[str] = []

    r = None
    try:
        r = requests.get(url, timeout=20)
        status = r.status_code
        flag, issues = _status_to_flag(status)
        metrics.append({'name':'HTTP Status Codes','status':flag,'details':str(status)})
        top_issues += issues
    except Exception as e:
        metrics.append({'name':'HTTP Status Codes','status':'bad','details':str(e)})
        top_issues.append('Site unreachable')

    parsed = urlparse(url)
    if parsed.scheme == 'https':
        metrics.append({'name':'HTTPS Implemented','status':'good','details':'HTTPS in use'})
    else:
        metrics.append({'name':'HTTPS Implemented','status':'bad','details':'Not using HTTPS'})
        top_issues.append('HTTPS not enforced')

    try:
        html = r.text if r is not None else ''
        low = html.lower()
        has_title = '<title>' in low
        metrics.append({'name':'Missing Title Tags','status':'good' if has_title else 'bad','details':'Title present' if has_title else 'Missing <title>'})
        has_meta_desc = '<meta name="description"' in low
        metrics.append({'name':'Missing Meta Descriptions','status':'good' if has_meta_desc else 'warn','details':'Meta description present' if has_meta_desc else 'No meta description'})
    except Exception:
        pass

    psi_m = _run_psi(url, 'mobile'); psi_d = _run_psi(url, 'desktop')
    def _extract_scores(psi_json: Dict) -> Dict:
        if not psi_json: return {}
        cats = psi_json.get('lighthouseResult', {}).get('categories', {})
        audits = psi_json.get('lighthouseResult', {}).get('audits', {})
        score_perf = int((cats.get('performance', {}).get('score') or 0) * 100)
        return {
            'performance_score': score_perf,
            'LCP_ms': audits.get('largest-contentful-paint', {}).get('numericValue'),
            'FCP_ms': audits.get('first-contentful-paint', {}).get('numericValue'),
            'CLS': audits.get('cumulative-layout-shift', {}).get('numericValue'),
            'TBT_ms': audits.get('total-blocking-time', {}).get('numericValue'),
        }
    perf_m = _extract_scores(psi_m); perf_d = _extract_scores(psi_d)

    if perf_m:
        metrics.append({'name':'Mobile Performance Score','status':'good' if perf_m['performance_score']>=90 else ('warn' if perf_m['performance_score']>=70 else 'bad'), 'details':str(perf_m['performance_score'])})
        if perf_m.get('LCP_ms') is not None:
            metrics.append({'name':'LCP (mobile)','status':'good' if perf_m['LCP_ms']<=2500 else ('warn' if perf_m['LCP_ms']<=4000 else 'bad'), 'details':str(perf_m['LCP_ms'])})
    if perf_d:
        metrics.append({'name':'Desktop Performance Score','status':'good' if perf_d['performance_score']>=90 else ('warn' if perf_d['performance_score']>=70 else 'bad'), 'details':str(perf_d['performance_score'])})

    good = sum(1 for m in metrics if m['status']=='good')
    warn = sum(1 for m in metrics if m['status']=='warn')
    bad  = sum(1 for m in metrics if m['status']=='bad')
    health_score = max(0, min(100, int(100 * (good + warn*0.6) / max(1,(good+warn+bad)) )))

    tech_perf   = perf_m.get('performance_score', 0) or health_score
    mobile_score= perf_m.get('performance_score', 0) or health_score

    category_scores = {
        'Overall Site Health': health_score,
        'Crawlability & Indexation': max(0, health_score - 5),
        'On-Page SEO': max(0, health_score - 10),
        'Technical & Performance': tech_perf,
        'Mobile & Usability': mobile_score,
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
