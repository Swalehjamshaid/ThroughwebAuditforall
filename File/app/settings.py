
import os

# App + Branding
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-this")
BRAND_NAME = os.getenv("BRAND_NAME", "FF Tech")

# Admin
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# Logging & Boot
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
RUN_DB_INIT = os.getenv("RUN_DB_INIT", "1").strip() == "1"

# PageSpeed Insights API
GOOGLE_PSI_API_KEY = os.getenv("GOOGLE_PSI_API_KEY")

# SMTP / SendGrid
MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.sendgrid.net")
MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "apikey")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
MAIL_FROM = os.getenv("MAIL_FROM", "noreply@example.com")
MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() == "true"

# Reporting
REPORT_VALIDITY_DAYS = int(os.getenv("REPORT_VALIDITY_DAYS", "90"))
