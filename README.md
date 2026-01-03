
# FF Tech — Website Audit SaaS (Railway-ready, fixed)

Drop this repo into GitHub, connect it on Railway, attach your Postgres, and deploy.

## Deploy on Railway
1. Create/attach a **PostgreSQL** service.
2. On the **App service → Variables → Add variable reference**, choose **`DATABASE_URL`** from the Postgres service.
3. Optional email vars: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `MAIL_FROM`.
4. Optional `SECRET_KEY`.
5. Deploy. After start:
   - `GET /health` → `{ "status": "ok" }`
   - Visit `/register` → confirm via email → login → `/dashboard`.

## Notes
- Dockerfile normalizes CRLF → LF and runs `start.sh` via bash to avoid Exec format errors.
- `railway.json` is at repo root and points to `File/Dockerfile`.
- Gunicorn binds to `${PORT:-8080}` by default.

## Local run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="postgresql://user:pass@host:5432/db"
export SECRET_KEY="change-this"
python app/app/main.py
# or
gunicorn app.app.main:app --bind 0.0.0.0:8080 --workers 2
```
