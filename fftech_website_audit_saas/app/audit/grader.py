
from typing import Dict

WEIGHTS = {'executive':0.10,'overall':0.10,'crawlability':0.20,'onpage':0.25,'performance':0.20,'mobile_security_intl':0.10,'opportunities':0.05}

def overall_score(category_scores: Dict[str,float]) -> float:
    total = 0.0
    for k,w in WEIGHTS.items(): total += category_scores.get(k,0.0)*w
    return round(total,2)

def to_grade(score: float) -> str:
    return 'A+' if score>=97 else 'A' if score>=93 else 'A-' if score>=90 else 'B+' if score>=87 else 'B' if score>=83 else 'B-' if score>=80 else 'C+' if score>=77 else 'C' if score>=73 else 'C-' if score>=70 else 'D'
