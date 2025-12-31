
# FF Tech – AI Powered Website Audit SaaS (Zero‑Touch Railway + Complete Multi‑page UI) – v4.3

**Upload to GitHub → Deploy from GitHub on Railway → Done.**

### v4.3 Changes (fix healthcheck)
- **Gunicorn + Uvicorn worker** startup (more robust in production containers)
- Dockerfile installs `tzdata`, `sqlite3`, and `curl` for health diagnostics
- Requirements include `python-multipart` and `gunicorn`
- Same full multi‑page templates: `base`, `landing`, `register`, `register_done`, `verify_success`, `login`, `results`, `audit_history`, `schedule`, `admin_dashboard`

### Deploy steps
1. Push to **GitHub**.
2. Railway → **New Project → Deploy from GitHub**.
3. (Optional) Add **Postgres** → Attach (injects `DATABASE_URL`).
4. (Optional) Set SMTP vars → email verification & scheduled emails.
5. Generate domain → open `/health` then `/`.

