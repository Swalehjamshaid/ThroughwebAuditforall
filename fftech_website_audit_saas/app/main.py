import os
import json
import asyncio
import smtplib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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

UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL      = os.getenv("BASE_URL", "http://localhost:8000")

SMTP_HOST     = os.getenv("SMTP_HOST")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

Base.metadata.create_all(bind=engine)

# ---- Startup schema patches ----
def _ensure_schedule_columns():
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS daily_time VARCHAR(8) DEFAULT '09:00';"))
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) DEFAULT 'UTC';"))
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS email_schedule_enabled BOOLEAN DEFAULT FALSE;"))
            conn.commit()
    except Exception:
        pass

def _ensure_user_columns():
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();"))
            conn.commit()
    except Exception:
        pass

_ensure_schedule_columns()
_ensure_user_columns()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

METRIC_LABELS = {
    "status_code": "Status Code", "content_length": "Content Length (bytes)",
    "content_encoding": "Compression", "cache_control": "Caching",
    "hsts": "HSTS", "xcto": "X-Content-Type-Options", "xfo": "X-Frame-Options",
    "csp": "Content-Security-Policy", "set_cookie": "Set-Cookie", "title": "HTML <title>",
    "title_length": "Title Length", "meta_description_length": "Meta Description Length",
    "meta_robots": "Meta Robots", "canonical_present": "Canonical Link Present",
    "has_https": "Uses HTTPS", "robots_allowed": "Robots Allowed", "sitemap_present": "Sitemap Present",
    "images_without_alt": "Images Missing alt", "image_count": "Image Count",
    "viewport_present": "Viewport Meta Present", "html_lang_present": "<html lang> Present",
    "h1_count": "H1 Count", "normalized_url": "Normalized URL", "error": "Fetch Error",
}

def _present_metrics(metrics: dict) -> dict:
    out = {}
    for k, v in (metrics or {}).items():
        label = METRIC_LABELS.get(k, k.replace("_", " ").title())
        if isinstance(v, bool): v = "Yes" if v else "No"
        out[label] = v
    return out

def _to_category_scores_dict(cs_list_or_dict):
    if isinstance(cs_list_or_dict, dict):
        return {str(k): int(v) for k, v in cs_list_or_dict.items() if isinstance(v, (int, float))}
    out = {}
    for item in (cs_list_or_dict or []):
        try: out[str(item["name"])] = int(item["score"])
        except Exception: continue
    return out

def _build_chart_data(category_scores_dict: dict, metrics_raw: dict, overall: int, grade: str) -> dict:
    cat_labels = list(category_scores_dict.keys())
    cat_values = [int(category_scores_dict.get(k, 0)) for k in cat_labels]
    boolean_candidates = ["has_https", "robots_allowed", "sitemap_present", "canonical_present", "viewport_present", "html_lang_present", "hsts", "xcto", "xfo", "csp"]
    passed = failed = 0
    boolean_items = []
    for key in boolean_candidates:
        val = metrics_raw.get(key, None)
        if isinstance(val, bool):
            boolean_items.append({"label": METRIC_LABELS.get(key, key), "value": val})
            if val: passed += 1
            else: failed += 1
    numeric_candidates = ["image_count", "images_without_alt", "title_length", "meta_description_length", "h1_count", "content_length"]
    numeric_labels, numeric_values = [], []
    for key in numeric_candidates:
        val = metrics_raw.get(key, None)
        if isinstance(val, (int, float)):
            numeric_labels.append(METRIC_LABELS.get(key, key))
            numeric_values.append(int(val))
    return {
        "category_scores": {"labels": cat_labels, "datasets": [{"label": "Scores", "data": cat_values, "backgroundColor": "#7c4dff"}]},
        "boolean_summary": {"labels": ["Passed", "Failed"], "datasets": [{"data": [passed, failed], "backgroundColor": ["#00c853", "#ff5252"]}], "items": boolean_items},
        "numeric_metrics": {"labels": numeric_labels, "datasets": [{"label": "Value", "data": numeric_values, "backgroundColor": "#40c4ff"}]},
        "health_gauge": {"value": int(overall), "grade": grade}
    }

def _normalize_url(raw: str) -> str:
    if not raw or not raw.strip(): return raw
    s = raw.strip()
    p = urlparse(s)
    if not p.scheme: s = "https://" + s; p = urlparse(s)
    return f"{p.scheme}://{p.netloc}{p.path or '/'}"

def _url_variants(u: str) -> list:
    p = urlparse(u); host = p.netloc; path = p.path or "/"; scheme = p.scheme
    cands = [f"{scheme}://{host}{path}"]
    alt_host = host[4:] if host.startswith("www.") else f"www.{host}"
    cands.extend([f"{scheme}://{alt_host}{path}", f"http://{host}{path}", f"http://{alt_host}{path}"])
    seen, ordered = set(), []
    for c in cands:
        if c not in seen: ordered.append(c); seen.add(c)
    return ordered

def _fallback_result(url: str) -> dict:
    return {"category_scores": {"Performance": 65, "SEO": 68, "Security": 70}, "metrics": {"error": "Fetch failed", "normalized_url": url}, "top_issues": ["Fetch failed; using baseline."]}

def _robust_audit(url: str) -> tuple[str, dict]:
    base = _normalize_url(url)
    for cand in _url_variants(base):
        try:
            res = run_basic_checks(cand)
            if _to_category_scores_dict(res.get("category_scores")): return cand, res
        except Exception: continue
    return base, _fallback_result(base)

current_user = None

@app.middleware("http")
async def session_middleware(request: Request, call_next):
    global current_user
    token = request.cookies.get("session_token")
    if token:
        try:
            data = decode_token(token)
            db = SessionLocal()
            u = db.query(User).filter(User.id == data.get("uid")).first()
            if u and getattr(u, "verified", False): current_user = u
            db.close()
        except Exception: pass
    return await call_next(request)

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user})

@app.post("/audit/open")
async def audit_open(request: Request):
    form = await request.form(); url = form.get("url")
    if not url: return RedirectResponse("/", status_code=303)
    norm, res = _robust_audit(url)
    cs_dict = _to_category_scores_dict(res["category_scores"])
    score = compute_overall(cs_dict); grade = grade_from_score(score)
    sum_txt = summarize_200_words(norm, cs_dict, res.get("top_issues", []))
    charts = _build_chart_data(cs_dict, res.get("metrics", {}), int(score), grade)
    return templates.TemplateResponse("audit_detail_open.html", {
        "request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user, "website": {"id": None, "url": norm},
        "audit": {"created_at": datetime.utcnow(), "grade": grade, "health_score": int(score), "exec_summary": sum_txt, 
                  "category_scores": [{"name": k, "score": v} for k, v in cs_dict.items()], "metrics": _present_metrics(res.get("metrics", {})), 
                  "top_issues": res.get("top_issues", []), "charts": charts}
    })

@app.get("/report/pdf/open")
async def report_pdf_open(url: str):
    norm, res = _robust_audit(url); cs_dict = _to_category_scores_dict(res["category_scores"])
    score = compute_overall(cs_dict); grade = grade_from_score(score)
    sum_txt = summarize_200_words(norm, cs_dict, res.get("top_issues", []))
    path = "/tmp/certified_audit_open.pdf"
    render_pdf(path, UI_BRAND_NAME, norm, grade, int(score), [{"name": k, "score": v} for k, v in cs_dict.items()], sum_txt)
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Audit.pdf")

@app.get("/auth/register")
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user})

@app.post("/auth/register")
async def register_post(request: Request, email: str = Form(...), password: str = Form(...), confirm_password: str = Form(...), db: Session = Depends(get_db)):
    if password != confirm_password: return RedirectResponse("/auth/register?mismatch=1", status_code=303)
    if db.query(User).filter(User.email == email).first(): return RedirectResponse("/auth/login?exists=1", status_code=303)
    u = User(email=email, password_hash=hash_password(password), verified=False); db.add(u); db.commit()
    token = create_token({"uid": u.id, "email": u.email}, expires_minutes=1440)
    send_verification_email(u.email, token)
    return RedirectResponse("/auth/login?check_email=1", status_code=303)

@app.get("/auth/verify")
async def verify(request: Request, token: str, db: Session = Depends(get_db)):
    try:
        data = decode_token(token); u = db.query(User).filter(User.id == data["uid"]).first()
        if u: u.verified = True; db.commit(); return RedirectResponse("/auth/login?verified=1", status_code=303)
    except Exception: pass
    return RedirectResponse("/auth/login?error=1", status_code=303)

@app.get("/auth/login")
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user})

def _send_magic_login_email(to_email: str, token: str) -> bool:
    if not (SMTP_HOST and SMTP_USER): return False
    link = f"{BASE_URL.rstrip('/')}/auth/magic?token={token}"
    html = f"<h3>Magic Login</h3><p>Click: <a href='{link}'>{link}</a></p>"
    msg = MIMEMultipart("alternative"); msg["Subject"] = "Magic Login"; msg["From"] = SMTP_USER; msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls(); s.login(SMTP_USER, SMTP_PASSWORD); s.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception: return False

@app.post("/auth/magic/request")
async def magic_request(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == email).first()
    if u and u.verified:
        t = create_token({"uid": u.id, "email": u.email, "type": "magic"}, expires_minutes=15)
        _send_magic_login_email(u.email, t)
    return RedirectResponse("/auth/login?magic_sent=1", status_code=303)

@app.get("/auth/magic")
async def magic_login(request: Request, token: str, db: Session = Depends(get_db)):
    global current_user
    try:
        data = decode_token(token); uid = data.get("uid")
        u = db.query(User).filter(User.id == uid).first()
        if u and u.verified and data.get("type") == "magic":
            current_user = u; st = create_token({"uid": u.id, "email": u.email}, expires_minutes=43200)
            r = RedirectResponse("/auth/dashboard", status_code=303)
            r.set_cookie(key="session_token", value=st, httponly=True, secure=BASE_URL.startswith("https"), samesite="Lax")
            return r
    except Exception: pass
    return RedirectResponse("/auth/login?error=1", status_code=303)

@app.post("/auth/login")
async def login_post(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    global current_user
    u = db.query(User).filter(User.email == email).first()
    if not u or not verify_password(password, u.password_hash) or not u.verified:
        return RedirectResponse("/auth/login?error=1", status_code=303)
    current_user = u; t = create_token({"uid": u.id, "email": u.email}, expires_minutes=43200)
    r = RedirectResponse("/auth/dashboard", status_code=303)
    r.set_cookie(key="session_token", value=t, httponly=True, secure=BASE_URL.startswith("https"), samesite="Lax")
    return r

@app.get("/auth/logout")
async def logout(request: Request):
    global current_user; current_user = None
    r = RedirectResponse("/", status_code=303); r.delete_cookie("session_token"); return r

@app.get("/auth/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    if not current_user: return RedirectResponse("/auth/login", status_code=303)
    websites = db.query(Website).filter(Website.user_id == current_user.id).all()
    auds = db.query(Audit).filter(Audit.user_id == current_user.id).order_by(Audit.created_at.desc()).limit(10).all()
    avg = round(sum(a.health_score for a in auds)/len(auds), 1) if auds else 0
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user, "websites": websites,
        "trend": {"labels": [a.created_at.strftime('%d %b') for a in reversed(auds)], "values": [a.health_score for a in reversed(auds)], "average": avg},
        "summary": {"grade": (auds[0].grade if auds else "A"), "health_score": (auds[0].health_score if auds else 0)},
        "schedule": {"daily_time": getattr(sub, "daily_time", "09:00"), "timezone": getattr(sub, "timezone", "UTC"), "enabled": getattr(sub, "email_schedule_enabled", False)}
    })

@app.get("/auth/audit/new")
async def new_audit_get(request: Request):
    if not current_user: return RedirectResponse("/auth/login", status_code=303)
    return templates.TemplateResponse("new_audit.html", {"request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user})

@app.post("/auth/audit/new")
async def new_audit_post(request: Request, url: str = Form(...), enable_schedule: str = Form(None), db: Session = Depends(get_db)):
    if not current_user: return RedirectResponse("/auth/login", status_code=303)
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if not sub: sub = Subscription(user_id=current_user.id, plan="free", active=True, audits_used=0); db.add(sub); db.commit()
    if enable_schedule: sub.email_schedule_enabled = True; db.commit()
    w = Website(user_id=current_user.id, url=url); db.add(w); db.commit()
    return RedirectResponse(f"/auth/audit/run/{w.id}", status_code=303)

@app.get("/auth/audit/run/{website_id}")
async def run_audit(website_id: int, request: Request, db: Session = Depends(get_db)):
    if not current_user: return RedirectResponse("/auth/login", status_code=303)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    if not w: return RedirectResponse("/auth/dashboard", status_code=303)
    norm, res = _robust_audit(w.url); cs_dict = _to_category_scores_dict(res["category_scores"])
    score = compute_overall(cs_dict); grade = grade_from_score(score)
    a = Audit(user_id=current_user.id, website_id=w.id, health_score=int(score), grade=grade, exec_summary=summarize_200_words(norm, cs_dict, res.get("top_issues", [])),
              category_scores_json=json.dumps([{"name": k, "score": v} for k, v in cs_dict.items()]), metrics_json=json.dumps(res.get("metrics", {})))
    db.add(a); w.last_audit_at = a.created_at; w.last_grade = grade; db.commit()
    return RedirectResponse(f"/auth/audit/{w.id}", status_code=303)

@app.get("/auth/audit/{website_id}")
async def audit_detail(website_id: int, request: Request, db: Session = Depends(get_db)):
    if not current_user: return RedirectResponse("/auth/login", status_code=303)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    if not w or not a: return RedirectResponse("/auth/dashboard", status_code=303)
    cs = json.loads(a.category_scores_json or "[]"); m_raw = json.loads(a.metrics_json or "{}")
    return templates.TemplateResponse("audit_detail.html", {
        "request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user, "website": w,
        "audit": {"created_at": a.created_at, "grade": a.grade, "health_score": a.health_score, "exec_summary": a.exec_summary, "category_scores": cs, "metrics": _present_metrics(m_raw), "charts": _build_chart_data(_to_category_scores_dict(cs), m_raw, a.health_score, a.grade)}
    })

@app.get("/auth/report/pdf/{website_id}")
async def report_pdf(website_id: int, request: Request, db: Session = Depends(get_db)):
    if not current_user: return RedirectResponse("/auth/login", status_code=303)
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    path = f"/tmp/audit_{website_id}.pdf"
    render_pdf(path, UI_BRAND_NAME, w.url, a.grade, a.health_score, json.loads(a.category_scores_json or "[]"), a.exec_summary)
    return FileResponse(path, filename=f"Audit_{website_id}.pdf")

@app.get("/auth/schedule")
async def schedule_get(request: Request, db: Session = Depends(get_db)):
    return await dashboard(request, db)

@app.post("/auth/schedule")
async def schedule_post(request: Request, daily_time: str = Form(...), timezone: str = Form(...), enabled: str = Form(None), db: Session = Depends(get_db)):
    if not current_user: return RedirectResponse("/auth/login", status_code=303)
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if sub: sub.daily_time = daily_time; sub.timezone = timezone; sub.email_schedule_enabled = bool(enabled); db.commit()
    return RedirectResponse("/auth/dashboard", status_code=303)

@app.get("/auth/admin/login")
async def admin_login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user})

@app.post("/auth/admin/login")
async def admin_login_post(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    global current_user; u = db.query(User).filter(User.email == email, User.is_admin == True).first()
    if not u or not verify_password(password, u.password_hash): return RedirectResponse("/auth/admin/login", status_code=303)
    current_user = u; t = create_token({"uid": u.id, "email": u.email, "admin": True}, expires_minutes=43200)
    r = RedirectResponse("/auth/admin", status_code=303); r.set_cookie(key="session_token", value=t, httponly=True); return r

@app.get("/auth/admin")
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    if not current_user or not current_user.is_admin: return RedirectResponse("/auth/admin/login", status_code=303)
    return templates.TemplateResponse("admin.html", {"request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user, "websites": db.query(Website).all(), "admin_users": db.query(User).all(), "admin_audits": db.query(Audit).all()})

def _send_report_email(to_email: str, subject: str, html_body: str) -> bool:
    if not SMTP_HOST: return False
    msg = MIMEMultipart("alternative"); msg["Subject"] = subject; msg["From"] = SMTP_USER; msg["To"] = to_email; msg.attach(MIMEText(html_body, "html"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls(); s.login(SMTP_USER, SMTP_PASSWORD); s.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception: return False

async def _daily_scheduler_loop():
    while True:
        try:
            db = SessionLocal(); now_utc = datetime.utcnow()
            for sub in db.query(Subscription).filter(Subscription.email_schedule_enabled == True).all():
                try: tz = ZoneInfo(sub.timezone or "UTC")
                except Exception: tz = ZoneInfo("UTC")
                if now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz).strftime("%H:%M") == (sub.daily_time or "09:00"):
                    u = db.query(User).filter(User.id == sub.user_id).first()
                    if u and u.verified:
                        webs = db.query(Website).filter(Website.user_id == u.id).all()
                        body = "".join([f"<p>{w.url}: {w.last_grade or 'N/A'}</p>" for w in webs])
                        _send_report_email(u.email, f"Daily Report - {UI_BRAND_NAME}", f"<h3>Summary</h3>{body}")
            db.close()
        except Exception: pass
        await asyncio.sleep(60)

@app.on_event("startup")
async def _start_scheduler():
    asyncio.create_task(_daily_scheduler_loop())

@app.get("/api/audit/open/chart")
async def api_audit_open_chart(url: str):
    norm, res = _robust_audit(url); cs_dict = _to_category_scores_dict(res["category_scores"])
    score = int(compute_overall(cs_dict)); grade = grade_from_score(score)
    return JSONResponse({"url": norm, "health_score": score, "grade": grade, "charts": _build_chart_data(cs_dict, res.get("metrics", {}), score, grade), "top_issues": res.get("top_issues", [])})

@app.get("/api/audit/{website_id}/chart")
async def api_audit_chart(website_id: int, request: Request, db: Session = Depends(get_db)):
    if not current_user: return JSONResponse({"error": "unauthorized"}, status_code=401)
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    if not a: return JSONResponse({"error": "not_found"}, status_code=404)
    cs = _to_category_scores_dict(json.loads(a.category_scores_json or "[]"))
    return JSONResponse({"health_score": a.health_score, "grade": a.grade, "charts": _build_chart_data(cs, json.loads(a.metrics_json or "{}"), a.health_score, a.grade)})
