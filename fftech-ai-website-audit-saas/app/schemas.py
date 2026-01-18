
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any

class RequestLink(BaseModel):
    email: EmailStr

class AuditCreate(BaseModel):
    url: str

class AuditResponse(BaseModel):
    id: int
    url: str
    score: int
    grade: str
    coverage: int
    summary: str
    metrics: Dict[str, Any]
