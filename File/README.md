
# FF Tech AI Website Audit — Railway Deployable (A–I Metrics)

**Deploy Steps**
1) In Railway, link GitHub and deploy; provision PostgreSQL and set `DATABASE_URL`.
2) Set env vars: `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `MAX_PAGES`, `MAX_DEPTH`, `USE_CREATE_ALL=true` (fallback table creation).
3) Open `/ui` for the dashboard. Use magic link → verify (JWT) → run audit.

**Note**: Web‑vitals & backlink/authority metrics require external providers; placeholders are returned until integrated.

**Migrations**: `alembic upgrade head` (optional; fallback `create_all` enabled by default).
