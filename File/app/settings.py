
import os
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@fftech.app")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@123")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")
BRAND_NAME = "FF Tech"
REPORT_VALIDITY_DAYS = 30
