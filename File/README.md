
# FF Tech – Railway Ready App (Open + Registered Audit)

This repository is ready to deploy on Railway. It uses a **Dockerfile build** with a shell‑wrapped `CMD` so `${PORT}` expands correctly before Gunicorn starts.

## Why shell‑wrapped CMD?
On Railway, when a service builds from a **Dockerfile**, any UI "Start Command" override runs in **exec form** (no shell), so `$PORT` will **not** expand unless you explicitly use `/bin/sh -c`. The Dockerfile here already does that in `CMD`, so you can **clear the UI Start Command** and rely on this `CMD`.  
Docs: [Start Command](https://docs.railway.com/guides/start-command), [Build & Start Commands](https://docs.railway.com/reference/build-and-start-commands).

If you decide to keep a Start Command in the UI for a Dockerfile service, wrap it as:
```bash
/bin/sh -c "PORT=${PORT:-8000}; exec gunicorn app.main:app -b 0.0.0.0:${PORT} -w 2"
```

## Deploy steps
1. Push this repo to GitHub.
2. Create a new Railway project → **Deploy from GitHub**.
3. Railway will detect the **Dockerfile** (logs show "Using detected Dockerfile!").  
Docs: [Build from a Dockerfile](https://docs.railway.com/guides/dockerfiles).
4. In your service **Settings → Start Command**, leave it **empty** (or use the shell‑wrapped command shown above).  
Docs: [Start Command](https://docs.railway.com/guides/start-command).
5. Redeploy. Logs should show Gunicorn binding to a numeric port: `Listening at: http://0.0.0.0:<number>`.

## Environment variables
- `SECRET_KEY` (optional; default provided)
- `ADMIN_EMAIL`, `ADMIN_PASSWORD` (optional; defaults provided)
- `DATABASE_URL` (optional; defaults to SQLite `sqlite:///data.db`)  
You can set these in **Railway → Variables**.

## Endpoints
- `/` – Landing (Open Audit + links to Register/Login)
- `POST /audit` – Open Audit (limited metrics; no storage)
- `/results` – Registered Audit (full 140 metrics; history + report)
- `/history` – Audit history
- `/schedule` – Demo scheduling page
- `/admin/login` & `/admin/dashboard` – Admin portal
- `/report.pdf` – Certified PDF report
- `/healthz` – Health check

## Notes
- Email verification is stubbed: it writes a message with the verify link under `app/data/outbox/` so you can click it during demos (no SMTP needed).
- All 140 metrics are in `app/data/metrics_catalogue_full.json`.
- Templates live under `app/templates/`, static CSS under `app/static/css/`.

---

## Local run (optional)
```bash
pip install -r requirements.txt
export PORT=8000
gunicorn app.main:app -b 0.0.0.0:${PORT} -w 1 --log-level debug
```

## Project structure
```
app/
  __init__.py
  settings.py
  models.py
  security.py
  emailer.py
  audit_stub.py
  main.py
  data/
    metrics_catalogue_full.json
    users.json
    audits.json
  templates/
    base.html
    landing.html
    results.html
    register.html
    register_done.html
    set_password.html
    verify_success.html
    login.html
    audit_history.html
    schedule.html
    admin_dashboard.html
  static/css/style.css
Dockerfile
railway.json
requirements.txt
README.md
```
