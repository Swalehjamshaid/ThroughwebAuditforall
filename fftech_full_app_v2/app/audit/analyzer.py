
from typing import Dict, Any, List

async def analyze(url: str, competitors: List[str] | None) -> Dict[str, Any]:
    h = sum(ord(c) for c in url) % 100
    scores = {
        "seo": 60 + (h % 20) / 2,
        "performance": 50 + (h % 30) / 3,
        "accessibility": 55 + (h % 25) / 2.5,
        "best_practices": 58 + (h % 22) / 2.2,
    }
    metrics = {
        "pages_crawled": 10 + (h % 5),
        "images": 20 + (h % 7),
        "scripts": 5 + (h % 3),
    }
    return {"category_scores": scores, "metrics": metrics}
