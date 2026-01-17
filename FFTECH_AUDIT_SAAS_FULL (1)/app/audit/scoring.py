from typing import Dict

GRADE_BANDS = [
    (97, 'A+'), (90, 'A'), (85, 'A-'), (80, 'B+'), (75, 'B'), (70, 'B-'),
    (65, 'C+'), (60, 'C'), (55, 'C-'), (0, 'D')
]

CATEGORY_WEIGHTS = {
    'Overall Site Health': 0.20,
    'Crawlability & Indexation': 0.20,
    'On-Page SEO': 0.20,
    'Performance & Technical': 0.20,
    'Mobile, Security & International': 0.10,
    'Opportunities & ROI': 0.10,
}

PENALTIES = {
    'total_errors': 0.4,
    'total_warnings': 0.15,
    'http_4xx_pages': 0.3,
    'http_5xx_pages': 0.5,
    'broken_internal_links': 0.25,
    'broken_external_links': 0.15,
    'redirect_chains': 0.1,
    'missing_title_tags': 0.2,
    'duplicate_title_tags': 0.15,
    'missing_meta_descriptions': 0.15,
    'missing_h1': 0.2,
    'multiple_h1': 0.1,
    'large_uncompressed_images': 0.05,
}

def cap(x: float) -> float:
    return max(0.0, min(100.0, x))

def score_category(m: Dict[str, float]) -> Dict[str, float]:
    base = 100.0; s = {}
    s['Overall Site Health'] = cap(base - (m.get('total_errors',0)*PENALTIES['total_errors'] + m.get('total_warnings',0)*PENALTIES['total_warnings']))
    s['Crawlability & Indexation'] = cap(base - (
        m.get('http_4xx_pages',0)*PENALTIES['http_4xx_pages'] +
        m.get('http_5xx_pages',0)*PENALTIES['http_5xx_pages'] +
        m.get('broken_internal_links',0)*PENALTIES['broken_internal_links'] +
        m.get('broken_external_links',0)*PENALTIES['broken_external_links'] +
        m.get('redirect_chains',0)*PENALTIES['redirect_chains']
    ))
    s['On-Page SEO'] = cap(base - (
        m.get('missing_title_tags',0)*PENALTIES['missing_title_tags'] +
        m.get('duplicate_title_tags',0)*PENALTIES['duplicate_title_tags'] +
        m.get('missing_meta_descriptions',0)*PENALTIES['missing_meta_descriptions'] +
        m.get('missing_h1',0)*PENALTIES['missing_h1'] +
        m.get('multiple_h1',0)*PENALTIES['multiple_h1'] +
        m.get('large_uncompressed_images',0)*PENALTIES['large_uncompressed_images']
    ))
    perf_pen = 0.0
    if isinstance(m.get('lcp'), (int,float)):
        perf_pen += max(0, (m['lcp']-2500)/100)
    if isinstance(m.get('cls'), (int,float)):
        perf_pen += max(0, (m['cls']-0.1)*200)
    perf_pen += m.get('http_5xx_pages',0)*0.6 + m.get('large_uncompressed_images',0)*0.4
    s['Performance & Technical'] = cap(base - perf_pen)
    s['Mobile, Security & International'] = cap(100.0 if m.get('https_implementation') else 70.0)
    qws = float(m.get('quick_wins_score', 50))
    s['Opportunities & ROI'] = cap(110 - qws)
    return s

def overall_score(category_scores: Dict[str, float]) -> float:
    return round(sum(category_scores[k]*CATEGORY_WEIGHTS[k] for k in CATEGORY_WEIGHTS), 1)

def letter_grade(score: float) -> str:
    for cutoff, grade in GRADE_BANDS:
        if score >= cutoff: return grade
    return 'D'
