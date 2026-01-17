
# FF Tech – AI Powered Website Audit SaaS (Railway Root)

This archive is structured for Railway: `Procfile`, `requirements.txt`, and the `app/` folder are at the root.

- Open Audit: `/` (index) → `POST /audit/open` → `GET /report/pdf/open?url=...`
- Registered flow: `/register`, `/login`, `/dashboard`, `/audit/new`, `/audit/{id}`, `/report/pdf/{id}`
- PSI server-side enrichment; 5-page certified PDF with radar chart.

Run locally:
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```
