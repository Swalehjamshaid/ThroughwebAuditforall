
import yaml
from . import crawlability, security, performance_light, onpage, mobile, international

CATEGORIES = {
    'Crawlability & Indexation': crawlability.run,
    'Security & HTTPS':          security.run,
    'Technical & Performance':   performance_light.run,
    'On-Page SEO':               onpage.run,
    'Mobile & Usability':        mobile.run,
    'International SEO':         international.run,
}


def compute_score(all_metrics: dict):
    with open('config/scoring.yaml','r') as f:
        cfg = yaml.safe_load(f)
    penalties = cfg['penalties']; thresholds = cfg['thresholds']

    base = 100.0
    c = all_metrics.get('Crawlability & Indexation', {})
    base -= min(c.get('broken_internal_links',0)*penalties['broken_internal_links'], 30)
    base -= min(c.get('broken_external_links',0)*penalties['broken_external_links'], 20)
    base -= min(c.get('redirect_chains',0)*penalties['redirect_chains'], 20)

    s = all_metrics.get('Security & HTTPS', {})
    if not s.get('https', True): base -= 25
    for k,v in s.items():
        if k.startswith('header_') and v == 'missing':
            base -= penalties['header_missing']

    o = all_metrics.get('On-Page SEO', {})
    if not o.get('title_exists', True): base -= penalties['missing_title']*3
    if not o.get('meta_description_exists', True): base -= penalties['missing_meta_description']*2
    if not o.get('h1_exists', True): base -= penalties['missing_h1']*2
    base -= min(o.get('large_images',0)*penalties['large_images'], 20)

    m = all_metrics.get('Mobile & Usability', {})
    if not m.get('viewport_present', True): base -= penalties['no_viewport']*2

    i = all_metrics.get('International SEO', {})
    base -= min(i.get('hreflang_conflicts',0)*penalties['hreflang_issues'], 10)

    score = max(0, min(100, base))
    if score >= thresholds['A+']: grade='A+'
    elif score >= thresholds['A']: grade='A'
    elif score >= thresholds['B']: grade='B'
    elif score >= thresholds['C']: grade='C'
    elif score >= thresholds['D']: grade='D'
    else: grade='E'
    return score, grade


def run_all(url: str) -> dict:
    all_metrics = {}
    for name, func in CATEGORIES.items():
        try:
            all_metrics[name] = func(url)
        except Exception as e:
            all_metrics[name] = {"error": str(e)}
    return all_metrics

# basic subset for Open Audit
BASIC_CATEGORIES = {
    'Crawlability & Indexation': crawlability.run,
    'Security & HTTPS':          security.run,
    'Technical & Performance':   performance_light.run,
}

def run_all_basic(url: str) -> dict:
    all_metrics = {}
    for name, func in BASIC_CATEGORIES.items():
        try:
            all_metrics[name] = func(url)
        except Exception as e:
            all_metrics[name] = {"error": str(e)}
    return all_metrics


def compute_score_basic(all_metrics: dict):
    return compute_score(all_metrics)
