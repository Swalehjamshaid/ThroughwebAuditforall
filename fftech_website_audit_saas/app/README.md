# app/ – FF Tech AI Website Audit (Single Folder)

- FastAPI API with open & registered audit modes
- Passwordless email sign-in (magic link)
- 5-page executive PDF + PNG/XLSX/PPTX exports
- Railway-ready (set DATABASE_URL, SECRET_KEY, BASE_URL, SMTP vars)

Run locally:
```bash
uvicorn app.main:app --reload
```