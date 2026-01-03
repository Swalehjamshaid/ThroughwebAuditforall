
from .common import fetch

SEC_HEADERS = ['content-security-policy', 'strict-transport-security', 'x-frame-options', 'x-content-type-options', 'referrer-policy', 'permissions-policy']

def run(url: str) -> dict:
    metrics = {}
    resp = fetch(url)
    headers = {k.lower(): v for k, v in resp.headers.items()}

    metrics['https'] = str(resp.url).startswith('https://')
    for h in SEC_HEADERS:
        metrics[f'header_{h}'] = 'present' if h in headers else 'missing'

    metrics['mixed_content'] = 'detected' if not metrics['https'] else 'unknown'
    return metrics
