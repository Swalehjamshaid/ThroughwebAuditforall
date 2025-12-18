# WebAudit SaaS – Railway Integrated (v2)

This project is ready for Railway: Flask + SQLAlchemy (Postgres), Celery + Redis, Lighthouse CLI audits, Chart.js dashboard, email notifications.

## Railway Services
- web: `gunicorn --bind 0.0.0.0:${PORT:-8080} run:app`
- worker: `celery -A app.tasks.celery worker --loglevel=info`
- beat: `celery -A app.tasks.celery beat --loglevel=info`

## Variables
SECRET_KEY, DATABASE_URL, REDIS_URL, MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_DEFAULT_SENDER

## Local
pip install -r requirements.txt; set env vars; run gunicorn and celery processes.
