from typing import Dict, List

# Fake/basic checks to keep the app working end-to-end.
# In production, plug in PSI or your own crawling logic here.

def run_basic_checks(url: str) -> Dict:
    categories = {
        "Performance": 82,
        "SEO": 78,
        "Accessibility": 74,
        "Best Practices": 80,
        "Security": 70
    }
    metrics = [
        ("First Contentful Paint", "1.9s"),
        ("Largest Contentful Paint", "2.4s"),
        ("Total Blocking Time", "180ms"),
        ("Cumulative Layout Shift", "0.04"),
        ("Requests", "42"),
    ]
    top_issues = [
        "Optimize images using modern formats",
        "Reduce unused JavaScript",
        "Improve server response time",
        "Add meta descriptions",
        "Use accessible contrast for text"
    ]
    return {
        "category_scores": categories,
        "metrics": metrics,
        "top_issues": top_issues,
    }
