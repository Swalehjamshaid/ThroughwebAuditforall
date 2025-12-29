
# Read primitives from metrics
score = float(metrics.get(1, {}).get("value", 0.0))
grade = metrics.get(2, {}).get("value", grade_from_score(score))
category_breakdown = metrics.get(8, {}).get("value", {})

# ✅ Derive progress values for bars/cards so templates don't index rows
progress_overall = max(0.0, min(100.0, score))
progress_security = float(category_breakdown.get("security", 0))
progress_performance = float(category_breakdown.get("performance", 0))
progress_seo = float(category_breakdown.get("seo", 0))
progress_mobile = float(category_breakdown.get("mobile", 0))
progress_content = float(category_breakdown.get("content", 0))
