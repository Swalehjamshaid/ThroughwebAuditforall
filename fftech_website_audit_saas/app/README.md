
# FF Tech AI Website Audit SaaS (Backend)

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Railway Start Command
```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Variables
- DATABASE_URL: provided by Railway Postgres
- SECRET_KEY, BACKEND_BASE_URL, RESEND_API_KEY (optional)

## Pages
- /            → index
- /dashboard   → dashboard
- /admin       → admin
- /auth/login  → login
- /auth/register → register
- /auth/verify → verify
- /audits/new  → new audit form
- /audits/{id} → audit detail
- /audits/{id}/open → read-only

## API
- POST /audits/open?url=...   → open audit (no storage)
- POST /auth/request-link      → send magic link
- GET  /auth/magic?token=...   → verify + issue JWT
- POST /audits/secure?url=...  → save (requires Bearer JWT)
- GET  /audits                 → list saved audits
- POST /audits/export/png      → chart PNG
- POST /audits/export/ppt      → PPTX (PNG fallback)
- POST /audits/export/xlsx     → XLSX (PNG fallback)
