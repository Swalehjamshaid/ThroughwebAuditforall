
# FF Tech – Railway-ready SaaS Audit (Integration-first)

This app is structured so `app/main.py` is a thin integration layer. All metrics and charts live in `app/metrics.py`. Database is fully integrated via Railway Postgres (`DATABASE_URL`). Schema creation is race-free using a PostgreSQL advisory lock; run Gunicorn with `--preload`.

## Deploy (Railway)
1. Create a project, add **Postgres** plugin.
2. Set Service **Root Directory** to `File/`.
3. Paste variables from `.env.example` into Railway → Variables (Raw Editor).
4. Deploy; the Dockerfile runs Gunicorn with `${PORT}` and `--preload`.

## Start Command (if not using Dockerfile)
```
gunicorn app.main:app -b 0.0.0.0:$PORT -w 2 --timeout 45
```

## Routes
- `/` landing
- `/register` → email verification → `/verify` → `/set_password`
- `/login`, `/logout`
- `/results?url=...` audit run (10 free audits; then `/subscribe`)
- `/history` past audits
- `/schedule` create daily/accumulated schedules
- `/admin/login`, `/admin/dashboard`
- `/report.pdf?url=...` FF Tech certificate (PDF)
- `/cron/daily`, `/cron/accumulated` (hook Railway scheduler)

## Notes
- PSI requires a valid `GOOGLE_PSI_API_KEY`.
- SMTP credentials required to send email via SendGrid.
- For production schema evolution, prefer Alembic migrations.
