from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class AuditRequest(BaseModel):
    url: str
    competitors: Optional[List[str]] = None

class AuditResponse(BaseModel):
    audit_id: Optional[int]
    url: str
    overall_score: float
    grade: str
    summary: Dict[str, Any]
    category_scores: Dict[str, float]
    metrics: Dict[str, Any]