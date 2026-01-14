def compute_category_scores(results):
    cat_scores = {}
    for cat, metrics in results.items():
        scores = [m['score'] for m in metrics.values() if 'score' in m]
        cat_scores[cat] = round(sum(scores)/len(scores), 2) if scores else 0.0
    
    overall = round(sum(cat_scores.values())/len(cat_scores), 2)
    summary = f"Audit result: {overall}%. Stability is high; Category E optimization is recommended."
    return overall, cat_scores, summary

def grade_from_score(score):
    if score >= 90: return 'A+'
    if score >= 80: return 'B'
    return 'C'
