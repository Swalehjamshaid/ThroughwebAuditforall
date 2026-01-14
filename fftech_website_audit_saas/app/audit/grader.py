def compute_category_scores(results):
    cat_scores = {}
    for cat, metrics in results.items():
        total_w, acc = 0.0, 0.0
        for m in metrics.values():
            w = float(m.get('weight', 1.0))
            s = m.get('score')
            if s is not None:
                acc += float(s) * w
                total_w += w
        cat_scores[cat] = round(acc / total_w, 2) if total_w > 0 else 0.0
    
    overall = round(sum(cat_scores.values()) / len(cat_scores), 2) if cat_scores else 0.0
    return overall, cat_scores

def grade_from_score(score):
    if score >= 90: return 'A'
    if score >= 80: return 'B'
    if score >= 70: return 'C'
    return 'D'
