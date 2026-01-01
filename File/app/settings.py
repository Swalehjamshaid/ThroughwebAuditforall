
import os

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-fftech')
DATABASE_URL = os.environ.get('DATABASE_URL')

MAIL_SERVER = os.environ.get('MAIL_SERVER')
MAIL_PORT = int(os.environ.get('MAIL_PORT', '0') or 0)
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
MAIL_FROM = os.environ.get('MAIL_FROM', 'noreply@fftech.local')
MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ('1','true','yes')

ADMIN_EMAIL = 'roy.jamshaid@gmail.com'
ADMIN_PASSWORD = 'Jamshaid,1981'
