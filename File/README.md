
# FF Tech – Website Audit SaaS (Open Audit + Registered Audit)

This project implements the platform requirements:
- **Open Audit** (no registration, no storage)
- **Registered Audit** (email verification, full 140+ metrics, history, scheduling, certified reports)

## Deploy on Railway
- Nixpacks: uses `railway.json` and `nixpacks.toml` to start Gunicorn with `app.main:app`.
- Dockerfile: included; set builder to DOCKERFILE if you prefer.

## Environment variables
- `SECRET_KEY` (optional) – Flask session secret; default provided
- `ADMIN_EMAIL`, `ADMIN_PASSWORD` (optional) – admin login; defaults provided
- `DATABASE_URL` (optional) – SQLAlchemy URL; defaults to SQLite `sqlite:///data.db`
- `SMTP_*` (optional) – not required; email sending is stubbed to `app/data/outbox/` for demo

## Local run
```bash
pip install -r requirements.txt
export PORT=8000
gunicorn app.main:app -b 0.0.0.0:${PORT} -w 1 --log-level debug
```
