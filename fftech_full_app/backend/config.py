from pydantic import BaseSettings

class Settings(BaseSettings):
    ENV: str = "development"
    SECRET_KEY: str = "change-me"
    BASE_URL: str = "http://localhost:8000"
    DATABASE_URL: str = "sqlite:///./fftech.db"
    BRAND_NAME: str = "FF Tech"
    BRAND_LOGO_PATH: str = "backend/static/img/logo.png"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
