from typing import Dict, Any
import requests
from ..config import get_settings

PSI_ENDPOINT = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed'

def fetch_psi(url: str, strategy: str = 'mobile') -> Dict[str, Any] | None:
    key = get_settings().PSI_API_KEY
    if not key:
        return None
    params = {'url': url, 'key': key, 'strategy': strategy, 'category': ['PERFORMANCE']}
    try:
        r = requests.get(PSI_ENDPOINT, params=params, timeout=30)
        if r.status_code != 200:
            return None
        audits = r.json().get('lighthouseResult',{}).get('audits',{})
        return {
            'lcp': audits.get('largest-contentful-paint',{}).get('numericValue'),
            'fcp': audits.get('first-contentful-paint',{}).get('numericValue'),
            'cls': audits.get('cumulative-layout-shift',{}).get('numericValue'),
            'total_blocking_time': audits.get('total-blocking-time',{}).get('numericValue'),
            'speed_index': audits.get('speed-index',{}).get('numericValue'),
            'time_to_interactive': audits.get('interactive',{}).get('numericValue'),
        }
    except requests.RequestException:
        return None
