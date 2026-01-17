from pydantic import BaseModel
from functools import lru_cache
import os

class Settings(BaseModel):
    ENV: str = os.getenv('ENV','development')
    BASE_URL: str = os.getenv('BASE_URL','http://localhost:8000')
    SECRET_KEY: str = os.getenv('SECRET_KEY','dev-secret')
    DATABASE_URL: str = os.getenv('DATABASE_URL','sqlite:///./local.db')

    SMTP_HOST: str | None = os.getenv('SMTP_HOST')
    SMTP_PORT: int | None = int(os.getenv('SMTP_PORT','587'))
    SMTP_USER: str | None = os.getenv('SMTP_USER')
    SMTP_PASSWORD: str | None = os.getenv('SMTP_PASSWORD')
    SMTP_FROM: str | None = os.getenv('SMTP_FROM')

    FREE_AUDIT_LIMIT: int = int(os.getenv('FREE_AUDIT_LIMIT','10'))
    ENABLE_SCHEDULER: bool = os.getenv('ENABLE_SCHEDULER','false').lower()=='true'
    ADMIN_TOKEN: str | None = os.getenv('ADMIN_TOKEN')

    RAILWAY_API_KEY: str | None = os.getenv('RAILWAY_API_KEY')
    GEMINI_API_KEY: str | None = os.getenv('GEMINI_API_KEY')
    PSI_API_KEY: str | None = os.getenv('PSI_API_KEY')
    AHREFS_API_KEY: str | None = os.getenv('AHREFS_API_KEY')
    SEMRUSH_API_KEY: str | None = os.getenv('SEMRUSH_API_KEY')

@lru_cache
def get_settings() -> Settings:
    return Settings()
