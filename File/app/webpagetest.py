
import time, requests, os

WPT_RUN = "https://www.webpagetest.org/runtest.php"
WPT_STATUS = "https://www.webpagetest.org/testStatus.php"
WPT_RESULT = "https://www.webpagetest.org/jsonResult.php"

def run_wpt_test(url: str, location: str = "Dulles:Chrome", api_key: str | None = None, timeout=180):
    """
    location examples: "Dulles:Chrome", "London:Chrome", "Frankfurt:Chrome", "Sydney:Chrome"
    returns dict with basic metrics or None on failure
    """
    if not api_key:
        return None

    params = {'url': url, 'f': 'json', 'location': location, 'runs': 1}
    headers = {'X-WPT-API-KEY': api_key}
    r = requests.post(WPT_RUN, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    resp = r.json()
    test_id = resp.get('data', {}).get('testId')
    if not test_id:
        return None

    # Poll status until complete
    start = time.time()
    while time.time() - start < timeout:
        s = requests.get(WPT_STATUS, params={'f':'json', 'test': test_id}, timeout=30).json()
        statusCode = s.get('statusCode')
        if statusCode == 200:
            break
        time.sleep(5)

    # Fetch results
    res = requests.get(WPT_RESULT, params={'test': test_id}, timeout=60).json()
    data = res.get('data', {})
    median = (data.get('median', {}) or data.get('average', {})).get('firstView', {})
    return {
        'location': location,
        'ttfb_ms': median.get('TTFB'),
        'fcp_ms': median.get('firstContentfulPaint'),
        'lcp_ms': median.get('largestContentfulPaint'),
        'loadTime_ms': median.get('loadTime'),
        'requests': median.get('requests'),
        'bytesInKB': (median.get('bytesIn') or 0) / 1024.0,
        'testId': test_id
    }
