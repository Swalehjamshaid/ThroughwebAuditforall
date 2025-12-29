
# fftech_audit/settings.py
import os

class Settings:
    DATABASE_URL       = os.getenv("DATABASE_URL", "sqlite:///./fftech_audit.db")
    APP_BASE_URL       = os.getenv("APP_BASE_URL", "http://localhost:8080")
    SECRET_KEY         = os.getenv("SECRET_KEY", "CHANGE_ME_32CHARS")
    USER_AGENT         = os.getenv("USER_AGENT", "FFTech-Audit/3.0 (+https://fftech.io)")
    FREE_AUDITS_LIMIT  = int(os.getenv("FREE_AUDITS_LIMIT", "10"))
    SCHEDULER_INTERVAL = int(os.getenv("SCHEDULER_INTERVAL", "60"))
    PORT               = int(os.getenv("PORT", "8080"))

    # Assets (toggle via .env; no rebuild)
    USE_CDN_ASSETS     = os.getenv("USE_CDN_ASSETS", "false").lower() == "true"
    GOOGLE_FONT_CSS    = os.getenv("GOOGLE_FONT_CSS",
                                   "https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap")
    CHARTJS_CDN        = os.getenv("CHARTJS_CDN",
                                   "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js")

    # Phase 2 switches
    ENABLE_AUTH        = os.getenv("ENABLE_AUTH", "false").lower() == "true"
    EMAIL_VERIFICATION_MODE = os.getenv("EMAIL_VERIFICATION_MODE", "link")  # link | code
    ALLOW_DEV_VERIFY   = os.getenv("ALLOW_DEV_VERIFY", "true").lower() == "true"

settings = Settings()
