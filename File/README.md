
# FF Tech – Railway Complete App (v4.5)

This build matches your folder structure (app/, Dockerfile, railway.json, README.md, requirements.txt, .env.example) and implements:
- Open Audit (spinner + Chart.js graphs)
- Registered Audit (Executive Summary + 150 metrics category-wise + Certified PDF)
- Registration (Name, Company, Email) → real **SMTP** verification → Set Password
- **Admin Login** with fixed credentials (`roy.jamshaid@gmail.com` / `Jamshaid,1981`)
- **PostgreSQL** integration via SQLAlchemy; auto-migration from JSON on first run

## Deploy (Railway)
1. Create a new Railway service from this folder/ZIP.
2. Add **PostgreSQL** service; Railway exposes `DATABASE_URL` automatically.
3. Variables (Service → Variables):
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
4. Deploy – uses `gunicorn app.main:app`.

## Notes
- Chart.js client-side via CDN + `<canvas>` is the recommended approach for quick visualization.
- SQLAlchemy expects the `postgresql` dialect in the URL; the app normalizes `postgres://` → `postgresql://` if needed.
- If SMTP variables are missing, the app writes `.eml` files in `app/data/outbox/` and still shows the verification link on the page.
