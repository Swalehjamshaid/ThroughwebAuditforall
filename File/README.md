
# FF Tech – AI Powered Website Audit SaaS (Zero‑Touch Railway + Complete Multi‑page UI)

**Upload to GitHub → Deploy from GitHub on Railway → Done.** This build includes:

- Root **Dockerfile** (Railway auto-detects) and **railway.json** (config-as-code)
- **FastAPI** with SQLite fallback (if Postgres not attached) and AUTO_VERIFY fallback (if SMTP not set)
- Complete multi‑page Jinja UI: `base`, `landing`, `register`, `register_done`, `verify_success`, `login`, `audit_history`, `results`, `schedule`, `admin_dashboard`
- Web UI **login/logout** using a secure HTTP‑only cookie with JWT inside
- 1100+ metrics audit stub, **Certified PDFs** (daily/accumulated), timezone scheduler
- Visually rich **results** page with charts (Chart.js) and accessible keyboard navigation for prompt suggestions

## Railway steps
1. Push this repo to **GitHub**.
2. Railway → **New Project → Deploy from GitHub**.
3. (Optional) Add **Postgres** → Attach (injects `DATABASE_URL`).
4. (Optional) Set SMTP vars; otherwise AUTO_VERIFY handles onboarding.
5. Generate domain → open your site.

## Primary UI routes
- `/` → landing
- `/register` → register form → `POST /ui/register` → `register_done`
- `/login` → login form → `POST /ui/login` → sets cookie → redirects home
- `/logout` → clears cookie → redirects home
- `/results?website_id=...` → latest audit with charts
- `/audit_history?website_id=...` → list of audits for the site
- `/schedule?website_id=...` → scheduler form → `POST /ui/schedule`
- `/admin/dashboard` → admin overview (users & websites)

## Notes
- Cookie is HTTP‑only; JWT expires in 120 minutes by default.
- The app will run even without Postgres/SMTP; attach them later for full power.

Refer to:
- Railway Config‑as‑Code and overrides → https://docs.railway.com/reference/config-as-code
- Railway Build Configuration (Dockerfile preference) → https://docs.railway.com/guides/build-configuration
- Railway Variables & Postgres injection → https://docs.railway.com/guides/variables
- Uvicorn host/port settings → https://uvicorn.dev/settings/
- Lighthouse audit categories → https://developer.chrome.com/docs/lighthouse/
- Core Web Vitals thresholds → https://developers.google.com/search/docs/appearance/core-web-vitals
- WCAG 2.2 accessibility standard → https://www.w3.org/TR/WCAG22/
- OWASP ASVS v5.0 security verification → https://owasp.org/www-project-application-security-verification-standard/
