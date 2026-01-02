
import os

# Read environment with sane defaults
SECRET_KEY = os.getenv('SECRET_KEY', 'change-this-in-prod')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@example.com')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
BRAND_NAME = os.getenv('BRAND_NAME', 'FFTech')
REPORT_VALIDITY_DAYS = int(os.getenv('REPORT_VALIDITY_DAYS', '30'))
DATABASE_URL = os.getenv('DATABASE_URL')  # Railway injects this
GOOGLE_PSI_API_KEY = os.getenv('GOOGLE_PSI_API_KEY')  # recommended for quota
WPT_API_KEY = os.getenv('WPT_API_KEY')  # optional
