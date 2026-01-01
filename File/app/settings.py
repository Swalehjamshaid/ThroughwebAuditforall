import os

# Flask secret key - always use a strong random value in production
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-fftech-change-in-production!!!')

# Database (if you plan to use SQLAlchemy later)
DATABASE_URL = os.environ.get('DATABASE_URL')

# Email configuration for sending verification emails
MAIL_SERVER = os.environ.get('MAIL_SERVER')
MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)  # Default to 587 (TLS)
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
MAIL_FROM = os.environ.get('MAIL_FROM', 'noreply@fftech.local')
MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ('true', '1', 'yes')
MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() in ('true', '1', 'yes')

# Admin credentials - STRONGLY recommended to use environment variables in production
# Current values are for local testing only
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'roy.jamshaid@gmail.com')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Jamshaid,1981')  # Change this in production!

# Environment mode
ENV = os.environ.get('ENV', 'development')

# Auto-verify users if no email server configured (useful for local dev)
AUTO_VERIFY = not bool(MAIL_SERVER and MAIL_USERNAME and MAIL_PASSWORD)
