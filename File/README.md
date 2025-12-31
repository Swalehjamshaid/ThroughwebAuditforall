
# FF Tech AI Website Audit — Railway Deployable (Full Metrics A–I)

This repository contains a FastAPI app that **executes and displays metrics for categories A–I** across Executive Summary, Health, Crawlability, On‑Page SEO, Performance/Technical, Mobile/Security/International, Competitor Analysis, Broken Links Intelligence, and Opportunities & ROI.

## Deploy on Railway
1. Push to GitHub, then in Railway: New Project → Deploy from GitHub → Select repo.
2. Provision **PostgreSQL** and set `DATABASE_URL` (Railway exposes `DATABASE_URL`, `PG*` vars).
3. Generate domain; open `/ui` for the dashboard.

## Environment
- `SECRET_KEY` (JWT) — required
- `ACCESS_TOKEN_EXPIRE_MINUTES` (default 60)
- `DATABASE_URL` — e.g. `postgresql+psycopg://user:pass@host:5432/db`
- `MAX_PAGES` (default 50), `MAX_DEPTH` (default 2) for crawling

## Migrations
```bash
alembic upgrade head
```

## Endpoints
- `POST /auth/send-link` → demo magic link token
- `POST /auth/verify` → returns `{ access_token, token_type }` (JWT)
- `POST /audit` → runs the full **metrics engine**, persists audit + category scores
- `GET /audit/{audit_id}` → returns stored result (all metrics)
- `GET /audit/{audit_id}/metrics` → category metric rows
- `GET /admin/audits` → **admin only** list of latest audits
- `GET /report/{audit_id}` → 5‑page certified PDF
- `GET /ui` → linked dashboard UI

## Notes
- Some metrics (e.g., **Domain Authority**, **Total Backlinks**, real Core Web Vitals) require external providers or headless rendering. The engine includes **best‑effort estimates** and leaves externally sourced values as 0/placeholder where applicable.
- For full web vitals, integrate Playwright/Lighthouse and wire results into `E` and `F` categories.
