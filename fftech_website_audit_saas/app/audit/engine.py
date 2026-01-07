
def run_checks(url: str) -> dict:
    return {
        'url': url,
        'score': 95,
        'issues': ['Missing alt text on 2 images', 'No sitemap.xml']
    }
