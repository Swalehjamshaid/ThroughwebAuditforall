
from pydantic import BaseSettings, AnyUrl
from typing import Optional

class Settings(BaseSettings):
    SECRET_KEY: str
    BASE_URL: str = "http://127.0.0.1:8000"
    ENV: str = "development"
    DATABASE_URL: str = "sqlite:///./local.db"

    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASS: Optional[str] = None
    SMTP_FROM: Optional[str] = None

    PSI_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"

settings = Settings()
