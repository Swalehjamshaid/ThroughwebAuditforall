import os

# Flask secret key - change in production!
SECRET_KEY = os.environ.get('SECRET_KEY', 'super-secret-change-this-in-production-123456')

# Admin login credentials
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'roy.jamshaid@gmail.com')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Jamshaid,1981')  # Change this!

# Database (optional)
DATABASE_URL = os.environ.get('DATABASE_URL')

# Email settings for verification
MAIL_SERVER = os.environ.get('MAIL_SERVER')
MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
MAIL_FROM = os.environ.get('MAIL_FROM', 'noreply@fftech.local')
MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ('true', '1', 'yes')

# Auto-verify users if no email server (good for testing)
AUTO_VERIFY = not bool(MAIL_SERVER and MAIL_USERNAME and MAIL_PASSWORD)

# Environment
ENV = os.environ.get('ENV', 'development')
