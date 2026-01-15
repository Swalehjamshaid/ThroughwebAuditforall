
from pydantic import BaseModel
import os

class Settings(BaseModel):
    # Email (Resend)
    RESEND_API_KEY: str = os.getenv('RESEND_API_KEY', '')
    RESEND_FROM_EMAIL: str = os.getenv('RESEND_FROM_EMAIL', 'onboarding@resend.dev')

    # Auth & Security
    ADMIN_EMAIL: str = os.getenv('ADMIN_EMAIL', '')
    MAGIC_EMAIL_ENABLED: bool = os.getenv('MAGIC_EMAIL_ENABLED', 'true').lower() == 'true'
    JWT_SECRET: str = os.getenv('JWT_SECRET', 'change_me')
    AUTH_SALT: str = os.getenv('AUTH_SALT', 'fftech_salt')
    AUTH_ITERATIONS: int = int(os.getenv('AUTH_ITERATIONS', '200000'))

    # App Configuration
    UI_BRAND_NAME: str = os.getenv('UI_BRAND_NAME', 'FF Tech')
    BASE_URL: str = os.getenv('BASE_URL', 'http://localhost:8000')
    PORT: int = int(os.getenv('PORT', '8080'))
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')

    # External APIs & Database
    DATABASE_URL: str = os.getenv('DATABASE_URL', 'sqlite:///./fftech.db')
    GOOGLE_PSI_API_KEY: str = os.getenv('GOOGLE_PSI_API_KEY', '')

settings = Settings()
