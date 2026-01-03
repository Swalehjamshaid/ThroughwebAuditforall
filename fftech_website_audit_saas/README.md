
# FF Tech – AI Powered Website Audit SaaS

Enterprise-grade SaaS to audit websites across 100+ metrics (SEO, performance, security, accessibility, compliance) with certified PDF reports, strict grading, and scheduling.

## Quick Start

1. **Environment variables** (Railway):
   - `DATABASE_URL` — Postgres connection string (provided by Railway)
   - `SECRET_KEY` — strong random string
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` — for email sending
   - `UI_BRAND_NAME` — optional (default: FF Tech)
   - `BASE_URL` — public URL of deployed app (used in email verification links)

2. **Run locally**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
export SECRET_KEY=change_me
uvicorn app.main:app --reload
```

3. **Deploy to Railway**
- Create a new project, add a **PostgreSQL** database, and set `DATABASE_URL`.
- Set `SECRET_KEY` and SMTP variables.
- Deploy. The `Procfile` starts the FastAPI app.

## Key Features
- Email-based registration with verification link
- Role-based access (User/Admin)
- Add multiple websites, schedule daily audits at a chosen time (timezone-aware)
- Daily and accumulated (historical) reports
- Strict grading (A+ to D) with category breakdown
- Certified PDF report with **FF Tech** logo
- Free tier: 10 audits; then $5/month subscription required

## Notes
- Some advanced metrics (Core Web Vitals) may use external APIs (e.g., PSI/Lighthouse). Provide API keys where needed.
- Admin panel provides user management, activity and system health.

