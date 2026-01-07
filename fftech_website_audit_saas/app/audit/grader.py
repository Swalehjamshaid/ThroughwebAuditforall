
def grade(report: dict) -> dict:
    score = report.get('score', 0)
    remarks = 'Excellent' if score >= 90 else 'Needs improvement'
    return {'score': score, 'remarks': remarks}
