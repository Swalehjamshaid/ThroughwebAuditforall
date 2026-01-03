
# FF Tech — Website Audit SaaS (Railway-ready)

This package is a production-ready **Flask** application integrated with **Railway PostgreSQL** (`DATABASE_URL`).

## Deploy on Railway
1. Create/attach a **PostgreSQL** service.
2. On the **App service → Variables → Add variable reference**, choose **`DATABASE_URL`** from the Postgres service.
3. Optional email vars: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `MAIL_FROM`.
4. Optional `SECRET_KEY`.
5. Deploy. After start:
   - `GET /health` → `{ "status": "ok" }`
   - Go to `/register` → confirm email (link) → login → `/dashboard`.

**References:**
- Railway PostgreSQL docs (variables incl. `DATABASE_URL`)
- Railway Help Station on build-time vs runtime

## Local run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="postgresql://user:pass@host:5432/db"
export SECRET_KEY="change-this"
python app/app/main.py
# or
gunicorn app.app.main:app --bind 0.0.0.0:8000 --workers 2
```
