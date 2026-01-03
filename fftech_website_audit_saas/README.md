# FF Tech – AI Powered Website Audit SaaS

A production-ready starter for an international SaaS that audits websites across 60–140+ metrics, with strict scoring & grading, certified PDF reports, email verification, usage limits, scheduling, and Railway Cloud deployment.

---

## Features
- FastAPI backend (Python) + SQLAlchemy ORM
- Railway PostgreSQL integration via `DATABASE_URL`
- Email-based registration with verification link
- JWT authentication (access tokens)
- Add websites, run on-demand audits, and schedule daily audits (TZ-aware)
- Strict scoring & grading (A+ … D)
- 200-word executive summary per audit
- Certified PDF report with FF Tech branding
- Free tier: 10 audits; then $5/month (Stripe-ready stub)
- Admin-ready endpoints (easy to extend)
- Single-page HTML dashboard (frontend/index.html)

## Quick Start (Local)

1. **Python 3.10+** recommended.
2. Create virtual env and install dependencies:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Set environment variables (see `.env.example`). On local you can export:
   ```bash
   export DATABASE_URL=postgresql+psycopg2://USER:PASS@HOST:PORT/DBNAME
   export SECRET_KEY=change_me
   export SMTP_HOST=your.smtp.host
   export SMTP_USER=username
   export SMTP_PASS=password
   ```
4. Run the app:
   ```bash
   uvicorn app.main:app --reload
   ```
5. Open docs: `http://localhost:8000/docs`

## Deploy on Railway

1. Create a new Railway project.
2. Add a **PostgreSQL** database plugin.
3. Copy the **connection string** and set it as `DATABASE_URL` in Railway **Variables**.
4. Set `SECRET_KEY`, `SMTP_*` variables (and later `STRIPE_*` for billing).
5. Ensure `Procfile` is present:
   ```
   web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
6. Deploy the repo (GitHub connect or `railway up`).

## API Overview

- `POST /auth/register` → starts registration, emails verification link
- `GET /auth/verify?token=...` → completes registration
- `POST /auth/login` → returns access token (JWT)
- `POST /websites` → add a website
- `GET /websites` → list websites
- `POST /audits/{website_id}/run` → run on-demand audit (quota enforced)
- `GET /audits/{audit_id}` → detailed audit result
- `GET /reports/{audit_id}/pdf` → download certified PDF
- `POST /audits/{website_id}/schedule` → schedule daily audits at a user-selected time
- Admin endpoints: stubbed in code; extend as needed

## Notes
- DB schema is created automatically on startup via SQLAlchemy metadata; for production, add Alembic.
- Core Web Vitals collection can be added via Playwright/Lighthouse (see comments in `audit_engine.py`).
- Replace the email "print" function with real SMTP or provider integration.
- For Stripe billing, implement `/billing/checkout` to create a checkout session and mark `subscriptions.plan='pro'` on success.

## License
MIT (for starter template)
