
# app/ – FF Tech AI Website Audit (FastAPI)

This **app** package is frontend-agnostic, ready for Railway. Keep `requirements.txt`, `.env` (or environment variables), `Dockerfile`, and `Procfile` **in the repository root**.

## Entrypoint (Uvicorn)
`uvicorn app.main:app --host 0.0.0.0 --port 8000`

## Routes
- `POST /api/auth/request-link` – email magic link
- `GET  /api/auth/verify?token=...` – verify
- `POST /api/audit` – run audit (open or registered)
- `GET  /api/audits/{id}` – fetch stored audit
- `GET  /api/reports/pdf/{audit_id}` – download 5-page PDF
- `POST /api/schedule` – create schedule (paid only)

## Notes
- Free users: up to 10 audits; no scheduling.
- PDFs saved in `storage/reports/` (create these folders at project root on deploy).
- PNG/XLSX/PPTX exports saved in `storage/exports/`.
