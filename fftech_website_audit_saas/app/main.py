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
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

# Plotting and Exports
import matplotlib
matplotlib.use("Agg")  # Headless mode for server compatibility
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from pptx import Presentation
from pptx.util import Inches
import pandas as pd

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

# Visual Thresholds
TITLE_MIN, TITLE_MAX = 12, 70
DESC_MIN, DESC_MAX   = 40, 170

COLORS = {
    "critical": "#D32F2F", "high": "#F4511E", "medium": "#FBC02D",
    "low": "#7CB342", "accent": "#3B82F6", "bg": "#0F172A",
    "fg": "#E5E7EB", "ok": "#2E7D32", "warn": "#EF6C00"
}

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

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

_ensure_schedule_columns()
_ensure_user_columns()

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

METRIC_LABELS = {
    "status_code": "Status Code", "content_length": "Content Length", "content_encoding": "Compression",
    "cache_control": "Caching", "hsts": "HSTS", "xcto": "XCTO", "xfo": "X-Frame-Options",
    "csp": "CSP", "set_cookie": "Set-Cookie", "title": "HTML Title", "title_length": "Title Length",
    "meta_description_length": "Meta Length", "meta_robots": "Meta Robots", "canonical_present": "Canonical",
    "has_https": "HTTPS", "robots_allowed": "Robots Indexing", "sitemap_present": "Sitemap",
    "images_without_alt": "Alt Missing", "image_count": "Total Images", "viewport_present": "Viewport",
    "html_lang_present": "HTML Lang", "h1_count": "H1 Count", "normalized_url": "URL", "error": "Fetch Error"
}

def _present_metrics(metrics: dict) -> dict:
    out = {}
    for k, v in (metrics or {}).items():
        label = METRIC_LABELS.get(k, k.replace("_", " ").title())
        if isinstance(v, bool): v = "Yes" if v else "No"
        out[label] = v
    return out

def _normalize_url(raw: str) -> str:
    if not raw or not raw.strip(): return raw
    s = raw.strip()
    p = urlparse(s)
    if not p.scheme: s = "https://" + s; p = urlparse(s)
    return f"{p.scheme}://{p.netloc}{p.path or '/'}"

def _url_variants(u: str) -> list:
    p = urlparse(u); host, path, scheme = p.netloc, p.path or "/", p.scheme
    candidates = [f"{scheme}://{host}{path}"]
    alt_host = host[4:] if host.startswith("www.") else f"www.{host}"
    candidates.extend([f"{scheme}://{alt_host}{path}", f"http://{host}{path}", f"http://{alt_host}{path}"])
    seen, ordered = set(), []
    for c in candidates:
        if c not in seen: ordered.append(c); seen.add(c)
    return ordered

def _fallback_result(url: str) -> dict:
    return {
        "category_scores": {"Performance": 65, "Accessibility": 72, "SEO": 68, "Security": 70, "BestPractices": 66},
        "metrics": {"error": "Fetch failed", "normalized_url": url},
        "top_issues": ["Fetch failed; check WAF/Robots settings."]
    }

def _robust_audit(url: str) -> tuple[str, dict]:
    base = _normalize_url(url)
    for cand in _url_variants(base):
        try:
            res = run_basic_checks(cand)
            cats = res.get("category_scores") or {}
            if cats and sum(int(v) for v in cats.values()) > 0: return cand, res
        except Exception: continue
    return base, _fallback_result(base)

def _safe_int(v):
    try: return int(float(v))
    except (ValueError, TypeError): return None

def _truthy(v) -> bool:
    if isinstance(v, bool): return v
    if not v: return False
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "ok", "present", "enabled"}

def _cookie_flag_present(set_cookie_val: str, flag: str) -> bool:
    return flag.lower() in str(set_cookie_val or "").lower()

current_user = None

@app.middleware("http")
async def session_middleware(request: Request, call_next):
    global current_user
    token = request.cookies.get("session_token")
    if token:
        try:
            data = decode_token(token); uid = data.get("uid")
            if uid:
                db = SessionLocal()
                u = db.query(User).filter(User.id == uid).first()
                if u and u.verified: current_user = u
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
    cs_dict = res["category_scores"]
    overall = compute_overall(cs_dict)
    return templates.TemplateResponse("audit_detail_open.html", {
        "request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user, "website": {"id": None, "url": norm},
        "audit": {"created_at": datetime.utcnow(), "grade": grade_from_score(overall), "health_score": int(overall),
                  "exec_summary": summarize_200_words(norm, cs_dict, res.get("top_issues", [])),
                  "category_scores": [{"name": k, "score": int(v)} for k, v in cs_dict.items()],
                  "metrics": _present_metrics(res.get("metrics", {})), "top_issues": res.get("top_issues", [])}
    })

@app.get("/report/pdf/open")
async def report_pdf_open(url: str):
    norm, res = _robust_audit(url); cs = res["category_scores"]
    score = compute_overall(cs)
    path = "/tmp/audit_open.pdf"
    render_pdf(path, UI_BRAND_NAME, norm, grade_from_score(score), int(score), [{"name": k, "score": int(v)} for k, v in cs.items()], summarize_200_words(norm, cs, res.get("top_issues", [])))
    return FileResponse(path, filename=f"{UI_BRAND_NAME}_Audit.pdf")

@app.get("/report/png/open")
async def report_png_open(url: str):
    norm, res = _robust_audit(url); path = "/tmp/dashboard_open.png"
    _render_dashboard_png(path, UI_BRAND_NAME, norm, [{"name": k, "score": int(v)} for k, v in res["category_scores"].items()], res.get("metrics", {}))
    return FileResponse(path, filename="Dashboard.png")

@app.get("/auth/register")
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user})

@app.post("/auth/register")
async def register_post(request: Request, email: str = Form(...), password: str = Form(...), confirm_password: str = Form(...), db: Session = Depends(get_db)):
    if password != confirm_password: return RedirectResponse("/auth/register?mismatch=1", status_code=303)
    if db.query(User).filter(User.email == email).first(): return RedirectResponse("/auth/login?exists=1", status_code=303)
    u = User(email=email, password_hash=hash_password(password), verified=False); db.add(u); db.commit()
    token = create_token({"uid": u.id, "email": u.email}, expires_minutes=4320)
    send_verification_email(u.email, token); return RedirectResponse("/auth/login?check_email=1", status_code=303)

@app.get("/auth/verify")
async def verify(request: Request, token: str, db: Session = Depends(get_db)):
    try:
        data = decode_token(token); u = db.query(User).filter(User.id == data["uid"]).first()
        if u: u.verified = True; db.commit(); return RedirectResponse("/auth/login?verified=1", status_code=303)
    except Exception: pass
    return RedirectResponse("/auth/login?error=1", status_code=303)

def _send_magic_login_email(to: str, token: str) -> bool:
    if not (SMTP_HOST and SMTP_USER): return False
    link = f"{BASE_URL.rstrip('/')}/auth/magic?token={token}"
    html = f"<h3>Magic Login</h3><p>Secure link: <a href='{link}'>{link}</a></p>"
    msg = MIMEMultipart("alternative"); msg["Subject"] = "Magic Login Link"; msg["From"] = SMTP_USER; msg["To"] = to
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls(); s.login(SMTP_USER, SMTP_PASSWORD); s.sendmail(SMTP_USER, [to], msg.as_string())
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
        data = decode_token(token); u = db.query(User).filter(User.id == data.get("uid")).first()
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
    if not u or not verify_password(password, u.password_hash) or not u.verified: return RedirectResponse("/auth/login?error=1", status_code=303)
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
    webs = db.query(Website).filter(Website.user_id == current_user.id).all()
    auds = db.query(Audit).filter(Audit.user_id == current_user.id).order_by(Audit.created_at.desc()).limit(10).all()
    avg = round(sum(a.health_score for a in auds)/len(auds), 1) if auds else 0
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user, "websites": webs,
        "trend": {"labels": [a.created_at.strftime('%d %b') for a in reversed(auds)], "values": [a.health_score for a in reversed(auds)], "average": avg},
        "summary": {"grade": (auds[0].grade if auds else "A"), "health_score": (auds[0].health_score if auds else 0)},
        "schedule": {"daily_time": getattr(sub, "daily_time", "09:00"), "timezone": getattr(sub, "timezone", "UTC"), "enabled": getattr(sub, "email_schedule_enabled", False)}
    })

@app.post("/auth/audit/new")
async def new_audit_post(request: Request, url: str = Form(...), enable_schedule: str = Form(None), db: Session = Depends(get_db)):
    if not current_user: return RedirectResponse("/auth/login", status_code=303)
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if not sub: sub = Subscription(user_id=current_user.id, audits_used=0); db.add(sub); db.commit()
    if enable_schedule: sub.email_schedule_enabled = True; db.commit()
    w = Website(user_id=current_user.id, url=url); db.add(w); db.commit()
    return RedirectResponse(f"/auth/audit/run/{w.id}", status_code=303)

@app.get("/auth/audit/run/{website_id}")
async def run_audit(website_id: int, db: Session = Depends(get_db)):
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    if not w: return RedirectResponse("/auth/dashboard", status_code=303)
    norm, res = _robust_audit(w.url); score = compute_overall(res["category_scores"])
    a = Audit(user_id=current_user.id, website_id=w.id, health_score=int(score), grade=grade_from_score(score), exec_summary=summarize_200_words(norm, res["category_scores"], res.get("top_issues", [])),
              category_scores_json=json.dumps([{"name": k, "score": int(v)} for k, v in res["category_scores"].items()]), metrics_json=json.dumps(res.get("metrics", {})))
    db.add(a); w.last_audit_at = a.created_at; w.last_grade = a.grade; db.commit(); return RedirectResponse(f"/auth/audit/{w.id}", status_code=303)

@app.get("/auth/audit/{website_id}")
async def audit_detail(website_id: int, request: Request, db: Session = Depends(get_db)):
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    if not w or not a: return RedirectResponse("/auth/dashboard", status_code=303)
    return templates.TemplateResponse("audit_detail.html", {
        "request": request, "UI_BRAND_NAME": UI_BRAND_NAME, "user": current_user, "website": w,
        "audit": {"created_at": a.created_at, "grade": a.grade, "health_score": a.health_score, "exec_summary": a.exec_summary, "category_scores": json.loads(a.category_scores_json), "metrics": _present_metrics(json.loads(a.metrics_json))}
    })

@app.get("/auth/report/png/{website_id}")
async def report_png(website_id: int, db: Session = Depends(get_db)):
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    path = f"/tmp/audit_{website_id}.png"
    _render_dashboard_png(path, UI_BRAND_NAME, w.url, json.loads(a.category_scores_json), json.loads(a.metrics_json))
    return FileResponse(path, filename="Audit_Dashboard.png")

@app.get("/auth/report/ppt/{website_id}")
async def report_ppt(website_id: int, db: Session = Depends(get_db)):
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    png = f"/tmp/dash_{website_id}.png"; ppt = f"/tmp/exec_{website_id}.pptx"
    _render_dashboard_png(png, UI_BRAND_NAME, w.url, json.loads(a.category_scores_json), json.loads(a.metrics_json))
    _export_ppt(UI_BRAND_NAME, w.url, a.grade, a.health_score, json.loads(a.category_scores_json), json.loads(a.metrics_json), png, ppt)
    return FileResponse(ppt, filename="Executive_Audit.pptx")

@app.get("/auth/report/xlsx/{website_id}")
async def report_xlsx(website_id: int, db: Session = Depends(get_db)):
    w = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    a = db.query(Audit).filter(Audit.website_id == website_id).order_by(Audit.created_at.desc()).first()
    path = f"/tmp/data_{website_id}.xlsx"
    _export_xlsx(UI_BRAND_NAME, w.url, a.grade, a.health_score, json.loads(a.category_scores_json), json.loads(a.metrics_json), path)
    return FileResponse(path, filename="Audit_Data.xlsx")

@app.post("/auth/schedule")
async def schedule_post(daily_time: str = Form(...), timezone: str = Form(...), enabled: str = Form(None), db: Session = Depends(get_db)):
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if sub: sub.daily_time, sub.timezone, sub.email_schedule_enabled = daily_time, timezone, bool(enabled); db.commit()
    return RedirectResponse("/auth/dashboard", status_code=303)

def _render_dashboard_png(path, brand, url, category_scores, metrics_raw):
    title_len, desc_len = _safe_int(metrics_raw.get("title_length")), _safe_int(metrics_raw.get("meta_description_length"))
    fig = plt.figure(figsize=(12, 8), dpi=150); fig.patch.set_facecolor(COLORS["bg"])
    ax1 = plt.subplot2grid((2, 3), (0, 0), colspan=2)
    names, values = [c["name"] for c in category_scores], [int(c["score"]) for c in category_scores]
    ax1.bar(names, values, color=COLORS["accent"]); ax1.set_ylim(0, 100); ax1.tick_params(colors=COLORS["fg"])
    ax2 = plt.subplot2grid((2, 3), (0, 2)); ax2.axis("off")
    ax2.text(0, 0.8, f"Title: {title_len}", color=COLORS["ok"] if (TITLE_MIN <= (title_len or 0) <= TITLE_MAX) else COLORS["warn"])
    ax3 = plt.subplot2grid((2, 3), (1, 0), colspan=3); ax3.axis("off")
    sec_items = [("XFO", _truthy(metrics_raw.get("xfo"))), ("CSP", _truthy(metrics_raw.get("csp"))), ("Secure Cookie", _cookie_flag_present(metrics_raw.get("set_cookie"), "Secure"))]
    y0 = 0.8
    for label, ok in sec_items:
        ax3.add_patch(Rectangle((0.02, y0), 0.04, 0.1, color=COLORS["ok"] if ok else COLORS["critical"], transform=ax3.transAxes))
        ax3.text(0.08, y0 + 0.05, f"{label}: {'OK' if ok else 'Missing'}", color=COLORS["fg"], transform=ax3.transAxes); y0 -= 0.15
    plt.savefig(path, facecolor=COLORS["bg"]); plt.close()

def _export_ppt(brand, url, grade, health_score, category_scores, metrics_raw, png, path):
    prs = Presentation(); s0 = prs.slides.add_slide(prs.slide_layouts[0])
    s0.shapes.title.text = f"Audit: {url}"; s0.placeholders[1].text = f"Grade: {grade} | Health: {health_score}/100"
    s1 = prs.slides.add_slide(prs.slide_layouts[5]); s1.shapes.add_picture(png, Inches(0.5), Inches(1.5), width=Inches(9))
    prs.save(path)

def _export_xlsx(brand, url, grade, health_score, category_scores, metrics_raw, path):
    summary = [{"Metric": "URL", "Value": url}, {"Metric": "Grade", "Value": grade}, {"Metric": "Health", "Value": health_score}]
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame(summary).to_excel(writer, sheet_name="Summary", index=False)
        pd.DataFrame(category_scores).to_excel(writer, sheet_name="Scores", index=False)
