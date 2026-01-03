from pydantic import BaseModel, EmailStr, AnyHttpUrl
from typing import Optional

class RegisterPayload(BaseModel):
    email: EmailStr
    password: str

class LoginPayload(BaseModel):
    email: EmailStr
    password: str

class WebsitePayload(BaseModel):
    url: AnyHttpUrl

class SchedulePayload(BaseModel):
    hour_local: int  # 0..23
    minute_local: int  # 0..59
    frequency: str  # "daily" or "weekly"

class AuditRunResponse(BaseModel):
    audit_id: int
    grade: str
    score: int
    summary: str
