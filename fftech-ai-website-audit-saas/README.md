
# FF Tech AI Website Audit SaaS

Production-ready **Python (FastAPI)** SaaS that audits websites, scores **200 metrics**, and generates a **5‑page executive PDF**. Built to be **frontend‑agnostic** and deployable on **Railway** with a managed Postgres database. Includes passwordless email login, open-access audits, user quotas, scheduling (paid), and branded exports.

---

## ✨ Highlights
- **Two modes:** Open access (no history) and **registered** (email magic link). 10 free audits for registered users.
- **200-metric framework** across *Executive, Health, Crawlability, On‑Page, Performance, Mobile/Security, Competitors, Broken Links, Opportunities/ROI*.
- **5‑page PDF** with charts, strengths/weaknesses, priorities, and FF Tech branding.
- **Beautiful UI** using **Bootstrap 5 + Chart.js** with **Dark/Light** toggle (templates included). Any frontend can consume the API.
- **Railway‑ready**: `Dockerfile`, `railway.toml`, Postgres integration, env‑config.

## Architecture
- **FastAPI** (`app/main.py`) exposes JSON APIs + server-rendered pages (Jinja).
- **SQLAlchemy** models with Postgres.
- **Passwordless auth** via signed magic links (JWT + SMTP).
- **Audit engine** (`app/audit/`) async crawler, parsers, metrics, **grader** (`grader.py`), competitors, opportunities, broken links.
- **Reports** (`app/report/`) create **PDF**, and **record.py** can export PNG, PPTX, XLSX.
- **Scheduler** (APScheduler) for paid users to run recurring audits + email PDF.

## Quickstart (Local)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill secrets
uvicorn app.main:app --reload
```
Open: http://127.0.0.1:8000

## Deploy to Railway
1. **Fork** this repo on GitHub.
2. In Railway: **New Project → Deploy from Repo**.
3. Add **Variables**:
   - `SECRET_KEY`, `BASE_URL`, `ENV=production`
   - `DATABASE_URL` *(Railway Postgres plugin auto‑sets)*
   - SMTP: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`
   - Optional: `PSI_API_KEY` for Core Web Vitals via PageSpeed Insights
4. Deploy. The service runs: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

## Auth (Email Magic Links)
- POST `/api/auth/request-link` with `email`.
- A signed URL is emailed. Opening it creates/returns a session token (HTTP‑only cookie) and redirects to **/dashboard**.

## Audits
- **Open access**: Use the form on the home page, or `POST /api/audit` with `{ "url": "https://example.com" }`.
- **Registered**: Audits are saved; free users capped at **10**. Paid users can schedule recurring audits and receive PDF via email.

## Scoring
- Every metric maps to a normalized **0–100** score with **weights per category**.
- The **grade** (A+…D) is derived from the weighted mean and **coverage/confidence**.
- Unavailable metrics (e.g., backlinks) don’t break the audit; they lower **coverage** and annotate the PDF.

## PDF
- 5 pages: **Executive**, **Health**, **Crawl/On‑Page**, **Performance/Mobile/Security**, **Opportunities/ROI + Broken Links + Competitors**.
- Branded, printable, with charts and written conclusions on each page.

## Frontend‑agnostic
- You can replace the templates with any SPA or headless frontend. All features are accessible via JSON APIs under `/api/*`.

## License
MIT
