from typing import List

def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))

def invert_scale(value: float, max_value: float = 100.0) -> float:
    if max_value <= 0: return 0.0
    return 100.0 - (value / max_value * 100.0)