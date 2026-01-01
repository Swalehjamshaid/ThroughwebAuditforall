
import random
from .security import ensure_nonempty_structs

# Build stub metrics for open/registered audit (randomized demo values)

def stub_open_metrics(url: str):
    site_health = {
        'score': round(random.uniform(6.5, 9.5), 2),
        'errors': random.randint(0, 30),
        'warnings': random.randint(5, 80),
        'notices': random.randint(20, 150),
        'grade': 'A'  # grade will be recalculated elsewhere
    }
    vitals = {
        'LCP': round(random.uniform(1.8, 4.5), 2),
        'FID': round(random.uniform(10, 100), 2),
        'CLS': round(random.uniform(0.01, 0.25), 2),
        'TBT': round(random.uniform(50, 600), 2)
    }
    cat_scores = {
        'Overall Health': round(random.uniform(6, 9), 2),
        'Crawlability': round(random.uniform(5, 9), 2),
        'On-Page': round(random.uniform(5, 9), 2),
        'Performance': round(random.uniform(4, 9), 2),
        'Security': round(random.uniform(6, 9), 2),
        'Mobile': round(random.uniform(5, 9), 2)
    }
    rows = []  # limited metrics in open audit
    sh, vt, cs, r = ensure_nonempty_structs(site_health, vitals, cat_scores, rows)
    return { 'site_health': sh, 'vitals': vt, 'cat_scores': cs, 'rows': r }
