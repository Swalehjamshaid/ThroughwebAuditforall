# FF Tech – AI-Powered Website Audit & Compliance SaaS (Starter)

A production-ready starter for an international SaaS that performs automated website audits (45+ metrics), grading, PDF-certified reporting, role-based administration, and time-zone aware scheduling. Built with **FastAPI + SQLAlchemy** and deployable on **Railway** with **Postgres** and **Lighthouse (Node.js)**.

## Key Capabilities
- User registration with email verification, encrypted passwords (bcrypt), and JWT login.
- Audit engine integrating Google Lighthouse and additional checks (security headers, SEO, accessibility, compliance hints).
- Time-zone aware scheduling (APScheduler) for daily/recurring/on-demand audits.
- Reporting: grading (A+…D), PDF-certified report with FF Tech branding.
- Admin panel endpoints with RBAC.
- Health check `/health`, production server via Gunicorn+Uvicorn.

## Quick Start (Local)
1. **Environment**
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   # Edit .env with your secrets and database URL
   ```
2. **Run (dev)**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
3. **Database migration (optional)**
   ```bash
   alembic init migrations
   # set sqlalchemy.url in alembic.ini to use env DATABASE_URL (see docs)
   alembic revision --autogenerate -m "init"
   alembic upgrade head
   ```

## Deploy on Railway
1. Create a new project, add **Postgres** plugin.
2. Set environment variables in Railway service:
   - `DATABASE_URL` → e.g. `postgresql+psycopg://user:P%40ss%3Aword%2F2025%3F@host:5432/db?sslmode=require`
   - `JWT_SECRET` → strong random string
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` (if using email)
3. Deploy. Railway will build using the provided `Dockerfile`. Health check path `/health`.

## Notable Files
- `app/main.py` – FastAPI app, routes registries, health endpoint.
- `app/db.py` – SQLAlchemy engine/session, Postgres URL normalization.
- `app/models.py` – User, AuditJob, AuditRun, AuditMetric, Report.
- `app/auth.py` – Password hashing (bcrypt) and JWT issuance/validation.
- `app/audit/lighthouse_runner.py` – Run Lighthouse via Node, parse JSON.
- `app/reporting/grading.py` – Score aggregation and letter grade.
- `app/reporting/pdf_report.py` – Generate branded PDF with ReportLab.
- `app/audit/scheduler.py` – APScheduler-based recurring jobs.
- `Dockerfile` – Python slim + Node + Lighthouse + Gunicorn startup.
- `railway.toml` – Health check config.

## Security Notes
- OWASP Top 10 mindful: hashed passwords, JWT with short expiry & refresh (extend as needed), RBAC checks, rate limiting (to add: e.g., via middleware), HTTPS enforced at platform.
- Use `sslmode=require` in Postgres URL on managed DBs.

## License
MIT – see `license.txt`.
