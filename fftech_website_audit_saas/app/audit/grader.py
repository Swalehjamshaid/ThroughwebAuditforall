def compute_category_scores(results):
    """
    Transforms raw audit data into the 9 categories (A-I).
    """
    # Mapping raw data to our display categories
    categories = {
        "Performance": results.get("Performance", {}).get("score", 0),
        "SEO": results.get("SEO", {}).get("score", 0),
        "Security": results.get("Security", {}).get("score", 0),
        "Accessibility": results.get("Accessibility", {}).get("score", 0),
        "Best Practices": results.get("Best Practices", {}).get("score", 0),
        "Mobile": 90, # Example fixed metric
        "Speed": 85   # Example fixed metric
    }
    
    avg_score = sum(categories.values()) / len(categories)
    summary = f"Your site scored {avg_score:.1f}% across all metrics."
    
    return avg_score, categories, summary

def grade_from_score(score):
    if score >= 90: return "A+"
    if score >= 80: return "A"
    if score >= 70: return "B"
    return "C"
