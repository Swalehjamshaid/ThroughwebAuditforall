FF Tech Website Audit SaaS — Complete app folder

Contents
- __init__.py
- db.py
- models.py
- auth.py
- email_utils.py
- main.py
- audit/engine.py, audit/grader.py, audit/report.py, audit/__init__.py
- templates/ (admin, audit_detail, audit_detail_open, base, base_open, base_register, dashboard, index, login, new_audit, register, verify)
- static/css, static/js, static/img

Notes
- Replace demo hashing with bcrypt/argon2 in production.
- Ensure SMTP_* and BASE_URL env vars are set.
- Start with: uvicorn app.main:app --reload
