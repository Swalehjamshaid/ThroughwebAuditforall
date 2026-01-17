
from pydantic import BaseModel

class Settings(BaseModel):
    BRAND_NAME: str = "ThroughwebAuditforall"

settings = Settings()
