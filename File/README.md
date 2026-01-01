
# FF Tech – Railway Complete App

- Open Audit (spinner + Chart.js graphs)
- Registered Audit (Executive Summary + **150 metrics** + Certified PDF)
- Registration → SMTP verification → Set Password → Login
- Admin Login (fixed creds) → Dashboard
- PostgreSQL via SQLAlchemy (JSON→DB migration)

## Railway PORT fix
Dockerfile wraps Gunicorn in `/bin/sh -c` so `${PORT}` expands at runtime.
