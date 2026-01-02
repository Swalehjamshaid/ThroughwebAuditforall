
import json, os, re
from urllib.parse import urlparse

def load(path):
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except Exception:
            return []

def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def normalize_url(url: str) -> str:
    url = (url or '').strip()
    if not url:
        return ''
    parsed = urlparse(url)
    if not parsed.scheme:
        url = 'https://' + url  # prefer https
    return url.rstrip('/')

def generate_summary(url, site_health, cat_scores):
    score = site_health.get('score', 0)
    grade = site_health.get('grade')
    focus = sorted(cat_scores.items(), key=lambda x: x[1])
    worst_three = ', '.join([f"{k} ({v:.1f})" for k, v in focus[:3]]) if focus else 'N/A'
    best_three = ', '.join([f"{k} ({v:.1f})" for k, v in focus[-3:]]) if focus else 'N/A'
    return (
        f"Audit for {url}: Overall {score:.2f}/10 ({grade}). Priority improvements: {worst_three}. "
        f"Strengths: {best_three}. Core Web Vitals and Lighthouse diagnostics are analyzed across mobile and desktop."
    )
