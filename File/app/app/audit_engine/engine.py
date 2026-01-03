
from . import crawlability, security, performance_light, onpage, mobile, international

CATEGORIES = {
    'Crawlability & Indexation': crawlability.run,
    'Security & HTTPS': security.run,
    'Performance (light)': performance_light.run,
    'On-Page SEO': onpage.run,
    'Mobile & Usability': mobile.run,
    'International SEO': international.run,
}

def compute_score(metrics: dict) -> float:
    score = 100
    bi = metrics.get('Crawlability & Indexation', {}).get('broken_internal_links', 0)
    be = metrics.get('Crawlability & Indexation', {}).get('broken_external_links', 0)
    score -= min(bi * 2, 20)
    score -= min(be, 10)
    sec = metrics.get('Security & HTTPS', {})
    for k, v in sec.items():
        if k.startswith('header_') and v == 'missing':
            score -= 3
    if not sec.get('https', True):
        score -= 15
    op = metrics.get('On-Page SEO', {})
    if not op.get('title_exists', True):
        score -= 10
    if not op.get('meta_description_exists', True):
        score -= 6
    if not op.get('h1_exists', True):
        score -= 6
    if not metrics.get('Mobile & Usability', {}).get('viewport_present', True):
        score -= 8
    return max(0, min(100, score))

def run_all(url: str) -> dict:
    all_metrics = {}
    for name, func in CATEGORIES.items():
        try:
            all_metrics[name] = func(url)
        except Exception as e:
            all_metrics[name] = {"error": str(e)}
    return all_metrics
