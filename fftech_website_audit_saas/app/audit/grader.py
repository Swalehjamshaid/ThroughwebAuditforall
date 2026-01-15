from typing import Dict, Tuple


GRADE_BANDS = [
    (97, 'A+'), (93, 'A'), (90, 'A-'),
    (87, 'B+'), (83, 'B'), (80, 'B-'),
    (77, 'C+'), (73, 'C'), (70, 'C-'),
    (0,  'D')
]


def grade_from_score(score: float) -> str:
    """
    Convert numerical score to letter grade using predefined bands.
    """
    for threshold, label in GRADE_BANDS:
        if score >= threshold:
            return label
    return 'D'  # fallback


def compute_category_scores(results: Dict[str, Dict]) -> Tuple[float, Dict[str, float]]:
    """
    Compute weighted average score for each category and overall average.
    
    Safely handles:
    - missing 'score' or 'weight' keys
    - None values
    - non-numeric values
    - empty categories
    - zero total weight
    
    Returns:
        (overall_score: float, category_scores: Dict[str, float])
    """
    cat_scores = {}
    
    for category, metrics in results.items():
        if not metrics:  # empty category
            cat_scores[category] = 0.0
            continue
            
        total_weighted = 0.0
        total_weight = 0.0
        
        for metric_key, m in metrics.items():
            # Get score safely - default to 0 if missing/invalid
            raw_score = m.get('score')
            try:
                score = float(raw_score) if raw_score is not None else 0.0
            except (TypeError, ValueError):
                score = 0.0
            
            # Get weight safely - default to 1.0
            raw_weight = m.get('weight', 1.0)
            try:
                weight = float(raw_weight) if raw_weight is not None else 1.0
            except (TypeError, ValueError):
                weight = 1.0
            
            total_weighted += score * weight
            total_weight += weight
        
        # Category average
        cat_scores[category] = round(total_weighted / total_weight, 2) if total_weight > 0 else 0.0
    
    # Overall average (simple mean of category scores)
    if not cat_scores:
        overall = 0.0
    else:
        overall = round(sum(cat_scores.values()) / len(cat_scores), 2)
    
    return overall, cat_scores


# Optional: more convenient combined function
def get_audit_result(results: Dict[str, Dict]) -> Dict:
    overall, cat_scores = compute_category_scores(results)
    return {
        "overall_score": overall,
        "grade": grade_from_score(overall),
        "category_scores": cat_scores
    }
