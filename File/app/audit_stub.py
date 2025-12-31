
from random import randint, uniform

def run_stub_audit(url: str) -> dict:
    metrics = {f"metric_{i}": uniform(0, 100) for i in range(1, 1101)}
    metrics.update({
        "broken_links": randint(0, 20),
        "security_headers": randint(60, 100),
        "https_enforced": True,
        "lcp_ms": int(uniform(1200, 3500)),
        "inp_ms": int(uniform(100, 350)),
        "cls": round(uniform(0.0, 0.25), 3),
    })
    return metrics

def compute_grade(overall_score: float) -> str:
    if overall_score >= 95: return "A+"
    if overall_score >= 90: return "A"
    if overall_score >= 80: return "B"
    if overall_score >= 70: return "C"
    return "D"
