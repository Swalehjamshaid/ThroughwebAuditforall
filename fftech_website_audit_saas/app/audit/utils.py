from typing import Iterable

def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))

def invert_scale(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 100.0
    pct = min(1.0, value / max_value)
    return (1.0 - pct) * 100.0