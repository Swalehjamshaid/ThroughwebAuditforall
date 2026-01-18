
from typing import Dict, Any
from .metrics_catalog import METRICS

GRADE_BANDS = [
    (97, 'A+'), (90, 'A'), (85, 'A-'), (80, 'B+'), (75, 'B'), (70, 'B-'),
    (65, 'C+'), (60, 'C'), (55, 'C-'), (0, 'D')
]

class Grader:
    def __init__(self, findings: Dict[str, Any]):
        self.findings = findings  # normalized findings computed by compute.py

    def score_metric(self, metric_id: int) -> Dict[str, Any]:
        m = METRICS.get(metric_id)
        name = m['name'] if m else f"Metric {metric_id}"
        cat = m['category'] if m else 'NA'
        data = self.findings.get(metric_id)
        if data is None:
            return {"id": metric_id, "name": name, "category": cat, "value": None, "score": None, "notes": "Not measured"}
        val = data.get('value')
        score = max(0, min(100, int(data.get('score', 0))))
        return {"id": metric_id, "name": name, "category": cat, "value": val, "score": score, "notes": data.get('notes', '')}

    def overall(self) -> Dict[str, Any]:
        weighted_scores = []
        total_weight = 0.0
        coverage_count = 0
        for mid, meta in METRICS.items():
            s = self.score_metric(mid)
            if s['score'] is not None:
                w = meta['weight']
                weighted_scores.append(s['score'] * w)
                total_weight += w
                coverage_count += 1
        overall = int(sum(weighted_scores) / total_weight) if total_weight else 0
        coverage = int(coverage_count / len(METRICS) * 100)
        grade = next(g for thr, g in GRADE_BANDS if overall >= thr)
        return {"score": overall, "grade": grade, "coverage": coverage}
