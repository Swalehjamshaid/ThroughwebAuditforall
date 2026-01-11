from urllib.parse import urlparse

def run_basic_checks(url: str) -> dict:
    """Return basic heuristic audit results.
    Replace with real network-based checks in production.
    """
    p = urlparse(url)
    host = p.netloc.lower()
    https = p.scheme == 'https'
    # Heuristic metrics
    metrics = {
        'normalized_url': f"{p.scheme}://{p.netloc}{p.path or '/'}",
        'has_https': https,
        'title_length': 20,  # placeholder
        'meta_description_length': 120,  # placeholder
        'xfo': True if https else False,
        'csp': True if 'example' in host else False,
        'hsts': https,
        'robots_allowed': True,
        'set_cookie': 'session=abc; Path=/; HttpOnly; Secure' if https else 'session=abc; Path=/'
    }
    # Category scores (simple demo)
    category_scores = {
        'Performance': 70,
        'Accessibility': 75,
        'SEO': 80,
        'Security': 65 if https else 55,
        'BestPractices': 72,
    }
    top_issues = []
    if not https:
        top_issues.append('Site does not use HTTPS by default.')
    if metrics['title_length'] < 12 or metrics['title_length'] > 70:
        top_issues.append('Title length out of recommended range.')
    if metrics['meta_description_length'] < 40 or metrics['meta_description_length'] > 170:
        top_issues.append('Meta description length out of recommended range.')
    return {
        'category_scores': category_scores,
        'metrics': metrics,
        'top_issues': top_issues,
    }
