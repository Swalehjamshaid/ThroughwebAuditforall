# FF Tech WebAudit SaaS (FastAPI + React) – Railway Ready

This repository contains a production-ready SaaS skeleton that implements:

- FastAPI backend (auth, audits, reports PDF, admin, billing/Stripe)
- React frontend (Vite) with a simple audit UI
- PostgreSQL via Railway `DATABASE_URL`
- Railpack-based build with `railpack.json`
- Config-as-code via `railway.toml`
- Dockerfile for local builds and Railway
- Rate limiting, CORS, JWT auth, bcrypt password hashing

## Quick Start (Local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload
# Frontend
cd frontend && npm i && npm run dev
```

## Deploy on Railway

1. Push this repo to GitHub.
2. In Railway, create a new project from the GitHub repo.
3. Add a **PostgreSQL** service. Railway will expose `DATABASE_URL` to your app. (Docs)  
4. (Optional) Add a **Redis** service if you plan to use scheduling/caching.
5. Set the service **Root Directory** to `/` (repo root). Do **not** set it to a file path.  
6. Ensure the config file path is the absolute path `/railway.toml` if you customize it in settings.  
7. Deploy. Railpack will build both frontend and backend using `railpack.json`.  

**Why this fixes your previous error**: Railpack looks for `railpack.json` in the root of the directory being built. Your logs showed the root set to `fftech-webaudit-saas/railway.toml` (a file), so it tried to open `railway.toml/railpack.json` and failed. With this repo, the root is the repository folder and `railpack.json` sits at the root, so detection works.

## Environment Variables

Copy `.env.example` to `.env` and set values. On Railway, define variables in the UI; `DATABASE_URL` comes from the Postgres service automatically.

## Migrations

Use Alembic if you want migrations. The pre-deploy command runs `alembic upgrade head` using `backend/alembic.ini`.

## API

- `POST /auth/register` – email, password
- `POST /auth/login` – OAuth2 password grant
- `POST /audits` – `{ url: "https://..." }` minimal audit
- `GET /reports/pdf` – sample certified PDF
- `POST /billing/create-checkout-session` – Stripe subscription session
- `GET /health` – healthcheck

## Security

- OWASP-aligned practices: JWT auth, rate limiting (SlowAPI), HTTPS assumed by Railway, password hashing (bcrypt).

## Notes

- The audit engine includes a minimal set; extend it to 45+ checks (SEO, performance, accessibility, compliance).
- Frontend calls backend relative paths; when deployed on the same service, this works out-of-the-box.

## License

© FF Tech. All rights reserved.
