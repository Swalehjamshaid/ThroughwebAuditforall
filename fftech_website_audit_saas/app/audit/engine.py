
from .analyzer import analyze
from .grader import compute_category_scores, grade_from_score


def run(url: str):
    payload = analyze(url)
    overall, cat_scores = compute_category_scores(payload['results'])
    grade = grade_from_score(overall)
    return {'url': url, 'score': overall, 'grade': grade, 'categories': cat_scores, 'details': payload}
