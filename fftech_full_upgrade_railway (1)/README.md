
# FF Tech – AI Powered Website Audit SaaS

This package contains an end-to-end, Railway-ready FastAPI app with:

- **Open Access Audit** (no registration): `/` landing + `/audit/open` + PDF `/report/pdf/open?url=...`
- **Registered Access** (email-verified users): standard dashboard & audit flow
- **PSI (PageSpeed Insights) enrichment** for performance / CWV
- **Certified 5-page PDF** report using ReportLab with an embedded **radar chart** rendered by Matplotlib

## Deploy on Railway
1. Set environment variables (Service → Variables):
   - `UI_BRAND_NAME` (optional)
   - `BASE_URL` (e.g., `https://<railway-subdomain>`)
   - `GOOGLE_PSI_API_KEY` (server-side only)
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` (optional for daily emails)
2. Ensure `Procfile` exists; Railway will boot with `uvicorn app.main:app`.
3. `pip install -r requirements.txt` locally if you run it on your machine.

## Quick Start (local)
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open: `http://localhost:8000`

- Run **Open Audit** from the landing page.
- Register / Login for the **registered flow**.

## Notes
- PSI v5 is designed to be called server-side and returns Lighthouse results programmatically. Keep your API key in env only.
- The PDF report is multi-page, brandable, and includes radar visuals.
