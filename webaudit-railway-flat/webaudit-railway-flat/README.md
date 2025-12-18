
# WebAudit SaaS – Railway Integrated (Flat Root)

This repository is ready to deploy on Railway. Files (Dockerfile, railway.toml, Procfile, run.py, app/) are at the repository root so Railpack will detect them.

## Railway Services
- web: `gunicorn --bind 0.0.0.0:${PORT:-8080} run:app`
- worker: `celery -A app.tasks.celery worker --loglevel=info`
- beat: `celery -A app.tasks.celery beat --loglevel=info`

## Environment Variables
SECRET_KEY, DATABASE_URL, REDIS_URL, MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_DEFAULT_SENDER

## Local Dev
pip install -r requirements.txt
export env vars
run `gunicorn run:app` and Celery processes
