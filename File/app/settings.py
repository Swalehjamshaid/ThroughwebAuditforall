
from pydantic_settings import BaseSettings
from pydantic import Field
class Settings(BaseSettings):
    ENV: str = Field(default="production")
    LOG_LEVEL: str = Field(default="info")
    PORT: int = Field(default=8000)
    DATABASE_URL: str | None = None
    SECRET_KEY: str = Field(default="change-me")
    EMAIL_FROM: str | None = None
    SMTP_HOST: str | None = None
    SMTP_PORT: int | None = None
    SMTP_USER: str | None = None
    SMTP_PASS: str | None = None
    TZ_DEFAULT: str = Field(default="UTC")
    AUTO_VERIFY: bool = Field(default=True)
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
settings = Settings()
