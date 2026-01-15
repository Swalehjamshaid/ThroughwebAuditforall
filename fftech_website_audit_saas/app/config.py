
import os
from pydantic import BaseModel

class Settings(BaseModel):
    ENV: str = os.getenv('ENV','development')
    SECRET_KEY: str = os.getenv('SECRET_KEY','change-me')
    BASE_URL: str = os.getenv('BASE_URL','http://localhost:8000')
    DATABASE_URL: str = os.getenv('DATABASE_URL','sqlite:///./fftech.db')
    BRAND_NAME: str = os.getenv('BRAND_NAME','FF Tech')
    BRAND_LOGO_PATH: str = os.getenv('BRAND_LOGO_PATH','app/static/img/logo.png')

settings = Settings()
