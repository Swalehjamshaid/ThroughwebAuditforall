
# FF Tech – AI Powered Website Audit SaaS (Zero‑Touch Railway + Complete Multi‑page UI) – v4.2

**Upload to GitHub → Deploy from GitHub on Railway → Done.**

### What’s in v4.2
- Full **multi‑page templates**: `base`, `landing`, `register`, `register_done`, `verify_success`, `login`, `results`, `audit_history`, `schedule`, `admin_dashboard` (matches your screenshot plus new pages). 
- **Dockerfile** hardened (installs `tzdata` + `sqlite3`) to ensure ZoneInfo & SQLite on Debian slim.
- **requirements.txt** includes `python-multipart` for form parsing.
- **SQLite fallback** so the app runs even without Postgres; attaches automatically to Railway Postgres when present.
- **AUTO_VERIFY** fallback so registration works even without SMTP.

### Deploy on Railway
1. Push to **GitHub**.
2. Railway → **New Project → Deploy from GitHub**.
3. (Optional) Add **Postgres** → Attach (Railway injects `DATABASE_URL`).
4. (Optional) Set SMTP variables → real email verification + scheduled emails.
5. Generate domain → open your site.

### Key routes (UI)
- `/` → landing
- `/register` → registration → `POST /ui/register` → `register_done`
- `/login` → login → `POST /ui/login` (secure HTTP‑only cookie)
- `/logout` → logout
- `/results?website_id=...` → latest audit with charts
- `/audit_history?website_id=...` → audit history table
- `/schedule?website_id=...` → scheduler (timezone prompt suggestions; use ↑/↓ to navigate, Enter to select)
- `/admin/dashboard` → admin overview (users & websites)

### Healthcheck
- Path is `/health`. If health fails, check logs. v4.2 includes the typical fixes (ZoneInfo/SQLite/forms).

