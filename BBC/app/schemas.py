from pydantic import BaseModel, HttpUrl, EmailStr
from typing import Any, Dict, Optional, List

class AuditRequest(BaseModel):
    url: HttpUrl

class AuditResponse(BaseModel):
    audit_id: Optional[int] = None
    target_url: str
    scores: Dict[str, Any]
    metrics: Dict[str, Any]
    pdf_url: Optional[str]

class MagicLinkRequest(BaseModel):
    email: EmailStr

class CompetitorRequest(BaseModel):
    main_url: HttpUrl
    competitors: List[HttpUrl]
