
# FF Tech – Railway Complete App (Ready for GitHub + Railway)

- Open Audit (spinner + Chart.js)
- Registered Audit (Executive Summary + **150 metrics** + Certified PDF)
- Registration → SMTP verification → Set Password → Login
- Admin Login (fixed creds) → Dashboard
- PostgreSQL via SQLAlchemy (JSON→DB migration)

## Railway PORT fix
Dockerfile wraps Gunicorn in `/bin/sh -c` so `${PORT}` expands at runtime. Do not set `ENV PORT` or `EXPOSE $PORT`.

## Env Variables
Set in Railway Service → Variables:
```
SECRET_KEY=<long random string>
DATABASE_URL=${{Postgres.DATABASE_URL}}
MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_USERNAME=apikey
MAIL_PASSWORD=<YOUR_SENDGRID_API_KEY>
MAIL_FROM=noreply@yourdomain.com
MAIL_USE_TLS=true
```
