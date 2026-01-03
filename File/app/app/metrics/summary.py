

def generate_summary(metrics: dict, score: float, grade: str, website: str) -> str:
    strengths = []
    weaknesses = []

    c = metrics.get('Crawlability & Indexation', {})
    bi = c.get('broken_internal_links', 0)
    if bi == 0:
        strengths.append('No broken internal links detected, indicating solid internal navigation.')
    else:
        weaknesses.append(f'{bi} broken internal links found; fix to improve crawlability and UX.')

    sec = metrics.get('Security & HTTPS', {})
    if sec.get('https', True):
        strengths.append('HTTPS is enabled, improving trust and protecting user data.')
    else:
        weaknesses.append('HTTPS missing on some pages; enforce HTTPS to prevent interception risks.')
    missing_headers = [k.replace('header_','') for k,v in sec.items() if k.startswith('header_') and v=='missing']
    if missing_headers:
        weaknesses.append('Missing security headers: ' + ', '.join(missing_headers))

    onp = metrics.get('On-Page SEO', {})
    if onp.get('title_exists', True):
        strengths.append('Title tags are present; ensure they remain focused and unique.')
    else:
        weaknesses.append('Title tags missing on some pages; add concise, keyword‑aligned titles.')
    if not onp.get('meta_description_exists', True):
        weaknesses.append('Meta descriptions absent; craft compelling summaries to boost CTR.')

    perf = metrics.get('Technical & Performance', {})
    mb = perf.get('total_page_size_mb', 0)
    if mb and mb > 3:
        weaknesses.append('Total page size is heavy; compress images and minify assets to reduce load.')

    mob = metrics.get('Mobile & Usability', {})
    if mob.get('viewport_present', True):
        strengths.append('Viewport meta is set, supporting responsive behavior across devices.')
    else:
        weaknesses.append('Viewport meta missing; add to ensure proper mobile rendering.')

    text = []
    text.append(f'This certified FF Tech audit assesses {website} across crawlability, on‑page SEO, performance, security, mobile usability, and international SEO. The site achieved {score:.1f}/100 (grade {grade}).')
    if strengths:
        text.append('Strengths: ' + ' '.join(strengths[:3]))
    if weaknesses:
        text.append('Key weaknesses: ' + ' '.join(weaknesses[:4]))
    text.append('Priority actions: fix broken links, enforce HTTPS and add missing security headers, optimize metadata, and reduce asset weight. Implement caching and image compression to improve Core Web Vitals and overall UX. Scheduled audits will track progress and produce daily and historical reports suitable for stakeholders and compliance use.')
    return ' '.join(text)
