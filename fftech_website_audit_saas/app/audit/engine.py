import re
from typing import Dict, Any, List
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Basic heuristics-based audit (standard library only)
def run_basic_checks(url: str) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    top_issues: List[str] = []
    cat = {"Performance": 60, "Accessibility": 70, "SEO": 65, "Security": 60}
    try:
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0 FFTechAudit'})
        with urlopen(req, timeout=10) as resp:
            status_code = resp.getcode()
            content_bytes = resp.read() or b''
            text = content_bytes.decode('utf-8', errors='ignore')
            metrics['status_code'] = status_code
            metrics['content_length'] = len(content_bytes)
            # Title
            m = re.search(r'<title>(.*?)</title>', text, re.IGNORECASE|re.DOTALL)
            title = (m.group(1).strip() if m else '')
            metrics['title'] = title
            metrics['title_length'] = len(title)
            # Canonical
            metrics['canonical_present'] = bool(re.search(r'rel=["']canonical["']', text, re.IGNORECASE))
            # HTTPS
            metrics['has_https'] = url.lower().startswith('https://')
            # <img alt>
            imgs = re.findall(r'<img[^>]*>', text, re.IGNORECASE)
            missing_alt = sum(1 for tag in imgs if not re.search(r'alt\s*=\s*["']', tag))
            metrics['images_without_alt'] = missing_alt
            # Category scores
            cat['Performance'] = max(30, min(100, 90 - (metrics['content_length'] // 100000)))
            cat['Accessibility'] = max(30, 90 - (missing_alt * 2))
            cat['SEO'] = max(30, 80 - (0 if metrics['canonical_present'] else 15) - (0 if metrics['title_length'] else 20))
            cat['Security'] = 85 if metrics['has_https'] else 55
            # Top issues
            if not metrics['has_https']:
                top_issues.append('Site is not served over HTTPS.')
            if metrics['title_length'] == 0:
                top_issues.append('Missing <title> tag.')
            if not metrics['canonical_present']:
                top_issues.append('Missing canonical link.')
            if missing_alt > 0:
                top_issues.append(f"{missing_alt} <img> tags without alt attribute.")
            if status_code >= 400:
                top_issues.append(f"HTTP status {status_code} detected.")
    except (HTTPError, URLError) as e:
        metrics['error'] = str(e)
        top_issues.append('Failed to fetch URL for audit; using default heuristics.')
    except Exception as e:
        metrics['error'] = str(e)
        top_issues.append('Unexpected error during audit.')
    return {
        'category_scores': cat,
        'metrics': metrics,
        'top_issues': top_issues,
    }
