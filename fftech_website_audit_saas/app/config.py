import os

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change")
JWT_ALG = "HS256"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://user:pass@localhost:5432/fftech")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")

CORS_ALLOW_ORIGINS = ["*"]
