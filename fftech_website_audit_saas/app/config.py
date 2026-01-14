import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App Identity
    UI_BRAND_NAME: str = "FF Tech"
    BASE_URL: str = "https://throughwebauditforall-production.up.railway.app"
    
    # Database Configuration - FIXED: Added DATABASE_URL attribute
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    
    # Security
    JWT_SECRET: str = "pvop2w6yluotcim1v36n3kd8adkcg5f3"
    
    # External APIs
    RESEND_API_KEY: str = "re_QXotQhhw_C9WoTXWETHuwkZZ8JbLiAccM"
    RESEND_FROM_EMAIL: str = "onboarding@resend.dev"
    GOOGLE_PSI_API_KEY: str = "AIzaSyDUVptDEm1ZbiBdb5m1DGjvKCW_LBVJMEw"

settings = Settings()
