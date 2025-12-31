
# FF Tech – Website Audit SaaS (Railway Ready, Error‑Free) – v4.4

Upload to **GitHub** → Deploy from **GitHub** on Railway → Works out‑of‑the‑box.

Included:
- `app/run.py` copied into image at `/app/run.py` (Railway start command compatibility)
- Hardened **Dockerfile** (`tzdata`, `sqlite3`, `curl` installed)
- **railway.json** config‑as‑code with `startCommand: python /app/run.py`
- Full **FastAPI** app with multi‑page Jinja templates (login/logout, admin, audit history, results, schedule)
- **SQLite fallback** if Postgres not attached; switches to `DATABASE_URL` automatically when attached
- SMTP optional; **AUTO_VERIFY** allows immediate testing without email server
- Healthcheck `/health` for Railway

## Deploy steps
1. Push all files to **GitHub**.
2. Railway → **New Project → Deploy from GitHub**.
3. (Optional) Add **Postgres** and attach → `DATABASE_URL` auto‑injected.
4. (Optional) Set SMTP variables; otherwise **AUTO_VERIFY** works.
5. Open your domain → `/health` should return 200.

## Notes
- `railway.json` enforces `startCommand: python /app/run.py`. If you prefer Dockerfile CMD (Gunicorn), set `startCommand` to empty.
- This package mirrors your folder layout (templates are in `app/templates` as in your screenshot).
