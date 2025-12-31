
import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    APP_NAME: str = os.getenv("APP_NAME", "FF Tech AI Website Audit")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///data/app.db")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-prod")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    MAX_PAGES: int = int(os.getenv("MAX_PAGES", "50"))
    MAX_DEPTH: int = int(os.getenv("MAX_DEPTH", "2"))

settings = Settings()
