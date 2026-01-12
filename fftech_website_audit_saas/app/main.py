import os
import json
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import Base, engine, SessionLocal
from .models import User, Website, Audit, Subscription
from .auth import hash_password, verify_password, create_token, decode_token
from .email_utils import send_verification_email
from .audit.engine import run_basic_checks
from .audit.grader import compute_overall, grade_from_score, summarize_200_words
from .audit.report import render_pdf

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ---------- Configuration ----------
UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL      = os.getenv("BASE_URL", "http://localhost:8000")

SMTP_HOST     = os.getenv("SMTP_HOST")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# ---------- Global Context Processor ----------
def inject_globals(request: Request):
    return {
        "datetime": datetime,
        "UI_BRAND_NAME": UI_BRAND_NAME,
        "year": datetime.utcnow().year,
        "now": datetime.utcnow()
    }
templates.context_processors.append(inject_globals)

# ---------- Database Initialization & SQL Patches ----------
Base.metadata.create_all(bind=engine)

def _ensure_schedule_columns():
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS daily_time VARCHAR(8) DEFAULT '09:00';"))
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) DEFAULT 'UTC';"))
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS email_schedule_enabled BOOLEAN DEFAULT FALSE;"))
            conn.commit()
    except Exception: pass

def _ensure_user_columns():
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();"))
            conn.commit()
    except Exception: pass

# --- ADDED: Auto-Verify SQL Logic ---
def _verify_admin_accounts():
    """Automatically verifies your specific email in the DB on startup."""
    try:
        with engine.connect() as conn:
            # Sets your specific email to verified so magic links work immediately
            conn.execute(text("UPDATE users SET verified = True WHERE email = :email"), {"email": "roy.jamshaid@gmail.com"})
            conn.commit()
            print("SQL UPDATE: Admin account verified successfully.")
    except Exception as e:
        print(f"SQL ERROR: Could not auto-verify account: {e}")

_ensure_schedule_columns()
_ensure_user_columns()
_verify_admin_accounts() # Execute the SQL update on startup

# ---------- Dependencies ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- Health Check ----------
@app.get("/health")
def health():
    return JSONResponse({"status": "ok"})

# ---------- Metrics Formatting ----------
METRIC_LABELS = {
    "status_code": "Status Code",
    "content_length": "Content Length (bytes)",
    "content_encoding": "Compression (Content-Encoding)",
    "cache_control": "Caching (Cache-Control)",
    "hsts": "HSTS (Strict-Transport-Security)",
    "xcto": "X-Content-Type-Options",
    "xfo": "X-Frame-Options",
    "csp": "Content-Security-Policy",
    "set_cookie": "Set-Cookie",
    "title": "HTML <title>",
    "title_length": "Title Length",
    "meta_description_length": "Meta Description Length",
    "meta_robots": "Meta Robots",
    "canonical_present": "Canonical Link Present",
    "has_https": "Uses HTTPS",
    "robots_allowed": "Robots Allowed",
    "sitemap_present": "Sitemap Present",
    "images_without_alt": "Images Missing alt",
    "image_count": "Image Count",
    "viewport_present": "Viewport Meta Present",
    "html_lang_present": "<html lang> Present",
    "h1_count": "H1 Count",
    "normalized_url": "Normalized URL",
    "error": "Fetch Error",
}

def _present_metrics(metrics: dict) -> dict:
    out = {}
    for k, v in (metrics or {}).items():
        label = METRIC_LABELS.get(k, k.replace("_", " ").title())
        if isinstance(v, bool): v = "Yes" if v else "No"
        out[label] = v
    return out

# ---------- Competitor Logic ----------
def _get_competitor_comparison(target_scores: dict):
    baseline = {"Performance": 82, "Accessibility": 88, "SEO": 85, "Security": 90, "BestPractices": 84}
    comparison = []
    for cat, score in target_scores.items():
        comp_val = baseline.get(cat, 80)
        diff = int(score) - comp_val
        comparison.append({
            "category": cat, "target": int(score), "competitor": comp_val,
            "gap": diff, "status": "Lead" if diff >= 0 else "Lag"
        })
    return comparison

# ---------- Audit Helpers ----------
def _normalize_url(raw: str) -> str:
    if not raw: return raw
    s = raw.strip()
    p = urlparse(s)
    if not p.scheme:
        s = "https://" + s
        p = urlparse(s)
    path = p.path or "/"
    return f"{p.scheme}://{p.netloc}{path}"

def _url_variants(u: str) -> list:
    p = urlparse(u)
    host, path, scheme = p.netloc, p.path or "/", p.scheme
    candidates = [f"{scheme}://{host}{path}"]
    if host.startswith("www."): candidates.append(f"{scheme}://{host[4:]}{path}")
    else: candidates.append(f"{scheme}://www.{host}{path}")
    candidates.append(f"http://{host}{path}")
    seen, ordered = set(), []
    for c in candidates:
        if c not in seen: ordered.append(c); seen.add(c)
    return ordered

def _fallback_result(url: str) -> dict:
    return {
        "category_scores": {"Performance": 65, "Accessibility": 72, "SEO": 68, "Security": 70, "BestPractices": 66},
        "metrics": {"error": "Fetch failed", "normalized_url": url},
        "top_issues": ["Fetch failed; using heuristic baseline.", "Verify URL accessibility."],
    }

def _robust_audit(url: str) -> tuple[str, dict]:
    base = _normalize_url(url)
    for candidate in _url_variants(base):
        try:
            res = run_basic_checks(candidate)
            cats = res.get("category_scores") or {}
            if cats and sum(int(v) for v in cats.values()) > 0:
                return candidate, res
        except Exception: continue
    return base, _fallback_result(base)

# ---------- Session Handling ----------
current_user = None

@app.middleware("http")
async def session_middleware(request: Request, call_next):
    global current_user
    try:
        token = request.cookies.get("session_token")
        if token:
            data = decode_token(token)
            uid = data.get("uid")
            if uid:
                db = SessionLocal()
                try:
                    u = db.query(User).filter(User.id == uid).first()
                    if u and getattr(u, "verified", False): current_user = u
                finally: db.close()
    except Exception: pass
    return await call_next(request)

# ---------- Routes ----------
@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "user": current_user})

@app.post("/audit/open")
async def audit_open(request: Request):
    form = await request.form()
    url = form.get("url")
    if not url: return RedirectResponse("/", status_code=303)
    normalized, res = _robust_audit(url)
    category_scores_dict = res["category_scores"]
    overall = compute_overall(category_scores_dict)
    
    return templates.TemplateResponse("audit_detail_open.html", {
        "request": request, "user": current_user, "website": {"id": None, "url": normalized},
        "audit": {
            "created_at": datetime.utcnow(), "grade": grade_from_score(overall), "health_score": int(overall),
            "exec_summary": summarize_200_words(normalized, category_scores_dict, res.get("top_issues", [])),
            "category_scores": [{"name": k, "score": int(v)} for k, v in category_scores_dict.items()],
            "metrics": _present_metrics(res.get("metrics", {})),
            "competitor_comparison": _get_competitor_comparison(category_scores_dict)
        },
        "chart": {"radar_labels": list(category_scores_dict.keys()), "radar_values": [int(v) for v in category_scores_dict.values()], "health": int(overall)}
    })

@app.post("/auth/magic/request")
@app.post("/auth/magic/request/")
async def magic_request(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == 1 or User.email == email).first() # Extra check to ensure Roy is found
    if u and getattr(u, "verified", False):
        token = create_token({"uid": u.id, "email": u.email, "type": "magic"}, expires_minutes=15)
        login_link = f"{BASE_URL.rstrip('/')}/auth/magic?token={token}"
        html_body = f"<h3>FF Tech Magic Login</h3><p>Click below to log in:</p><p><a href='{login_link}'>{login_link}</a></p>"
        
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"{UI_BRAND_NAME} Magic Link"
        msg["From"] = SMTP_USER
        msg["To"] = u.email
        msg.attach(MIMEText(html_body, "html"))
        
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [u.email], msg.as_string())
                print(f"EMAIL SUCCESS: Sent to {u.email}")
        except Exception as e:
            print(f"EMAIL FAIL: {e}")
            
    return RedirectResponse("/auth/login?magic_sent=1", status_code=303)

# ... (Auth and Dashboard routes continue)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), workers=1)
