
# fftech_full_app (Railway-ready)

## Deploy steps
1. Push this folder to GitHub (keep this structure).
2. On Railway, create:
   - a **Postgres** service
   - a **Web** service from this repo
3. In Web → **Variables**, add (link Postgres to auto-fill):
   - `DATABASE_URL = ${{Postgres.DATABASE_URL}}`
   - `PGHOST       = ${{Postgres.PGHOST}}`
   - `PGPORT       = ${{Postgres.PGPORT}}`
   - `PGUSER       = ${{Postgres.PGUSER}}`
   - `PGPASSWORD   = ${{Postgres.PGPASSWORD}}`
   - `PGDATABASE   = ${{Postgres.PGDATABASE}}`

> Do **not** define `PORT` — Railway sets it.

Start command is handled by `Dockerfile`/`railway.json`: `python run.py`.

## Test
- Health: `/auth/health`
- Home: `/`
- API: POST `/api/audit` with `{ "url": "https://example.com" }`

If you need SSL for Postgres, open `app/database.py` and uncomment `sslmode=require` lines.
