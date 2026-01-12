
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("RAILWAY_DATABASE_URL") or os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'app.db'}")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-please")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@fftech.ai")
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
FREE_AUDIT_LIMIT = int(os.getenv("FREE_AUDIT_LIMIT", "10"))
FREE_HISTORY_DAYS = int(os.getenv("FREE_HISTORY_DAYS", "30"))
FFTECH_BRAND = os.getenv("FFTECH_BRAND", "FF Tech AI Website Audit")
LOGO_PATH = str(BASE_DIR / 'static' / 'logo.png')
