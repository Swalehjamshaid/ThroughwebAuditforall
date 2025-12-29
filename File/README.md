
# FF Tech AI • Website Audit SaaS — Railway (with Scheduling)

Fully aligned with Railway's config-as-code (`railway.toml`) and includes:
- Open & Registered audits
- 5-page executive PDF emailed to registered users
- Scheduling endpoints: user picks **daily/weekly** and **exact time-of-day** with timezone

## Local Run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn fftech_audit.app:app --reload
```

## Railway Deploy
1. Push to GitHub → Create Railway project → Deploy from GitHub.
2. Add **Postgres** → set `DATABASE_URL`.
3. Set env vars from `.env.example` (BASE_URL, SMTP_*, SECRET_KEY).
4. Deploy. Railway uses `railway.toml` to start uvicorn.
5. Settings → Networking → Generate Domain for a public URL.

## Scheduling API
- **Set** schedule:
```http
POST /schedule/set
{
  "token": "SESSION_TOKEN",
  "url": "https://example.com",
  "frequency": "daily",        // or "weekly"
  "time_of_day": "09:30",       // HH:MM (24h)
  "timezone": "Asia/Karachi"    // IANA TZ
}
```
- **List** schedules:
```http
GET /schedule/list?token=SESSION_TOKEN
```
- **Disable** a schedule:
```http
POST /schedule/disable
{ "token": "SESSION_TOKEN", "schedule_id": 123 }
```

## Notes
- 5-page PDF via ReportLab.
- Static assets auto-mounted from root `/static` if present, else package static.
- For production DB changes, use migrations (Alembic) to add scheduling columns.
