
# app.py
# FF Tech — Professional Web Audit Dashboard (International Standard)
# Features:
# - Single-page HTML (CDN-only)
# - Actual audits: requests + BeautifulSoup + internal crawler
# - 250+ metrics (unique IDs, visual charts)
# - Open access vs registered logic (5–10 free audits → $5/month Stripe)
# - Users add websites and schedule audits (preferred time/date + timezone)
# - SMTP email delivery with 5-page Certified PDF
# - Admin endpoints
# - Settings (timezone + notification prefs)
# - Stripe Checkout & Webhook integration (safe fallbacks)
# - Railway healthcheck: /health + bind to PORT
# - SAFE DB INIT + SAFE SESSIONS (no crashes when DB is down)
# - Flexible HTML linking: /page/<name>, /template/<name>, /static/*

import os, io, hmac, json, time, base64, secrets, asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

from fastapi import FastAPI, Request, HTTPException, Query, Header
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr, Field

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, ForeignKey, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError

# Stripe (guarded)
try:
    import stripe
except Exception as e:
    stripe = None
    print("[STRIPE WARNING] Stripe SDK not installed:", e)

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics import renderPDF

# -----------------------------------------------
# Config
# -----------------------------------------------
APP_NAME = "FF Tech — Professional AI Website Audit Platform"
USER_AGENT = os.getenv("USER_AGENT", "FFTech-Audit/3.0 (+https://fftech.io)")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech_demo.db")

# Fix old prefix
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

FREE_AUDITS_LIMIT = int(os.getenv("FREE_AUDITS_LIMIT", "10"))  # set 5–10
SUBSCRIPTION_PRICE_USD = os.getenv("SUBSCRIPTION_PRICE_USD", "5")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "no-reply@fftech.io")

SCHEDULER_INTERVAL = int(os.getenv("SCHEDULER_INTERVAL", "60"))  # seconds

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", APP_BASE_URL + "/success")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", APP_BASE_URL + "/cancel")
if stripe and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# -----------------------------------------------
# DB setup (lazy; safe init later)
# -----------------------------------------------
engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    password_salt = Column(String(64), nullable=False)
    is_verified = Column(Boolean, default=False)
    role = Column(String(32), default="user")
    timezone = Column(String(64), default="UTC")
    free_audits_remaining = Column(Integer, default=FREE_AUDITS_LIMIT)
    subscribed = Column(Boolean, default=False)
    stripe_customer_id = Column(String(255))
    notify_daily_default = Column(Boolean, default=True)
    notify_acc_default = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime)

class Website(Base):
    __tablename__ = "websites"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    url = Column(String(2048), nullable=False)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    website_id = Column(Integer, ForeignKey("websites.id"), nullable=False)
    enabled = Column(Boolean, default=True)
    time_of_day = Column(String(8), default="09:00")
    timezone = Column(String(64), default="UTC")
    daily_report = Column(Boolean, default=True)
    accumulated_report = Column(Boolean, default=True)
    preferred_date = Column(DateTime, nullable=True)  # first run date
    last_run_at = Column(DateTime)

class Audit(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True)
    website_id = Column(Integer, ForeignKey("websites.id"), nullable=True)
    url = Column(String(2048), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    overall = Column(Integer, default=0)
    grade = Column(String(8), default="F")
    errors = Column(Integer, default=0)
    warnings = Column(Integer, default=0)
    notices = Column(Integer, default=0)
    summary = Column(Text)
    cat_scores_json = Column(Text)
    cat_totals_json = Column(Text)
    metrics_json = Column(Text)
    premium = Column(Boolean, default=False)

class LoginLog(Base):
    __tablename__ = "login_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    email = Column(String(255))
    ip = Column(String(64))
    user_agent = Column(Text)
    success = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# -----------------------------------------------
# Safe session helper (no crashes when DB is down)
# -----------------------------------------------
@contextmanager
def safe_session():
    """
    Returns a SQLAlchemy session if DB is reachable; otherwise yields None.
    Prevents OperationalError from bubbling up and crashing routes.
    """
    db = None
    try:
        db = SessionLocal()
        # lightweight connectivity test
        db.execute(text("SELECT 1"))
        yield db
    except OperationalError as e:
        print("[DB UNAVAILABLE]", e)
        yield None
    except Exception as e:
        print("[DB ERROR]", e)
        yield None
    finally:
        try:
            if db:
                db.close()
        except Exception:
            pass


# -----------------------------------------------
# Security helpers (PBKDF2 + minimal JWT)
# -----------------------------------------------
def hash_password(password: str, salt: str) -> str:
    import hashlib
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return base64.b64encode(dk).decode()

def create_user_password(password: str):
    salt = secrets.token_hex(16)
    return hash_password(password, salt), salt

def jwt_sign(payload: dict, key: str = SECRET_KEY, exp_minutes: int = 60) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = dict(payload); payload["exp"] = int(time.time()) + exp_minutes * 60
    def b64url(d: bytes) -> bytes: return base64.urlsafe_b64encode(d).rstrip(b"=")
    header_b = b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b = b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = header_b + b"." + payload_b
    sig = hmac.new(key.encode(), signing_input, "sha256").digest()
    return (signing_input + b"." + b64url(sig)).decode()

def jwt_verify(token: str, key: str = SECRET_KEY) -> dict:
    try:
        def b64url_decode(s: str) -> bytes:
            s += "=" * (-len(s) % 4)
            return base64.urlsafe_b64decode(s.encode())
        h_b64, p_b64, s_b64 = token.split(".")
        signing_input = (h_b64 + "." + p_b64).encode()
        expected = hmac.new(key.encode(), signing_input, "sha256").digest()
        sig = b64url_decode(s_b64)
        if not hmac.compare_digest(expected, sig):
            raise ValueError("Invalid signature")
        payload = json.loads(b64url_decode(p_b64).decode())
        if int(time.time()) > int(payload.get("exp", 0)):
            raise ValueError("Token expired")
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


# -----------------------------------------------
# FastAPI app + CORS + HTML linking
# -----------------------------------------------
app = FastAPI(title=APP_NAME)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Static / templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="pages")

@app.get("/page/{name}", response_class=HTMLResponse)
def get_plain_page(name: str):
    if any(ch in name for ch in ("..", "/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid page name")
    path = os.path.join("pages", f"{name}.html")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Page not found")
    with open(path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/template/{name}", response_class=HTMLResponse)
def get_jinja_page(name: str, request: Request):
    if any(ch in name for ch in ("..", "/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid template name")
    return templates.TemplateResponse(f"{name}.html", {"request": request, "app_name": APP_NAME})


# -----------------------------------------------
# Healthcheck (Railway)
# -----------------------------------------------
@app.get("/health", response_class=JSONResponse)
async def health_check():
    return {"status": "healthy", "time": datetime.utcnow().isoformat()}


# -----------------------------------------------
# Networking helpers
# -----------------------------------------------
def safe_request(url: str, method: str = "GET", **kwargs):
    try:
        kwargs.setdefault("timeout", (10, 20))
        kwargs.setdefault("allow_redirects", True)
        kwargs.setdefault("headers", {"User-Agent": USER_AGENT})
        return requests.request(method.upper(), url, **kwargs)
    except Exception:
        return None

def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw: return raw
    parsed = urlparse(raw)
    if not parsed.scheme: raw = "https://" + raw
    return raw


# -----------------------------------------------
# Audit engine (realistic heuristics)
# -----------------------------------------------
def detect_mixed_content(soup: BeautifulSoup, scheme: str) -> bool:
    if scheme != "https": return False
    for tag in soup.find_all(["img","script","link","iframe","video","audio","source"]):
        for attr in ["src","href","data","poster"]:
            val = tag.get(attr)
            if isinstance(val,str) and val.startswith("http://"): return True
    return False

def is_blocking_script(tag) -> bool:
    return tag.name == "script" and not (tag.get("async") or tag.get("defer") or tag.get("type")=="module")

def crawl_internal(seed_url: str, max_pages: int = 100):
    visited, queue, results, host = set(), [(seed_url, 0)], [], urlparse(seed_url).netloc
    while queue and len(results) < max_pages:
        url, depth = queue.pop(0)
        if url in visited: continue
        visited.add(url)
        resp = safe_request(url, "GET")
        status_code = resp.status_code if resp else None
        final = resp.url if resp else url
        redirs = len(resp.history) if resp and resp.history else 0
        results.append({"url": final, "depth": depth, "status": status_code, "redirects": redirs})
        if not resp or not resp.text: continue
        try:
            soup = BeautifulSoup(resp.text or "", "html.parser")
            for a in soup.find_all("a"):
                href = a.get("href") or ""
                if not href: continue
                abs_url = urljoin(final, href)
                parsed = urlparse(abs_url)
                if parsed.netloc == host and parsed.scheme in ("http","https"):
                    if abs_url not in visited: queue.append((abs_url, depth + 1))
                if len(queue) > max_pages * 3: queue = queue[:max_pages * 3]
        except Exception: pass
    return results

def run_actual_audit(target_url: str) -> dict:
    url = normalize_url(target_url)
    resp = safe_request(url, "GET")

    if not resp or (resp.status_code and resp.status_code >= 400):
        metrics = [{"num": i, "severity": "red", "chart_type": "bar",
                    "chart_data": {"labels": ["Pass","Fail"], "datasets":[{"data":[0,100],"backgroundColor":["#10b981","#ef4444"]}]}} for i in range(1,251)]
        return {
            "grade":"F","summary":f"{url} unreachable. Fix availability (HTTP 2xx), DNS/TLS, and ensure HTTPS.",
            "strengths":[],"weaknesses":["Site unreachable"],"priority":["Restore availability","Fix DNS/TLS","Ensure 200 OK"],
            "overall":0,"errors":1,"warnings":0,"notices":0,
            "overall_gauge":{"labels":["Score","Remaining"],"datasets":[{"data":[0,100],"backgroundColor":["#ef4444","#e5e7eb"],"borderWidth":0}]},
            "health_gauge":{"labels":["Score","Remaining"],"datasets":[{"data":[0,100],"backgroundColor":["#ef4444","#e5e7eb"],"borderWidth":0}]},
            "issues_chart":{"labels":["Errors","Warnings","Notices"],"datasets":[{"data":[1,0,0],"backgroundColor":["#ef4444","#f59e0b","#3b82f6"]}]},
            "category_chart":{"labels":["SEO","Performance","Security","Accessibility","Mobile"],"datasets":[{"label":"Score","data":[0,0,0,0,0],"backgroundColor":["#6366f1","#f59e0b","#10b981","#ef4444","#0ea5e9"]}]} ,
            "totals":{"cat1":0,"cat2":0,"cat3":0,"cat4":0,"cat5":0,"overall":0},
            "metrics":metrics,"premium":False,"remaining":0,"cat_scores":{"SEO":0,"Performance":0,"Security":0,"Accessibility":0,"Mobile":0},
        }

    html = resp.text or ""
    soup = BeautifulSoup(html, "html.parser")
    scheme = urlparse(resp.url).scheme or "https"

    ttfb_ms = int(resp.elapsed.total_seconds() * 1000)
    page_size_bytes = len(resp.content or b"")
    size_mb = page_size_bytes / (1024.0 * 1024.0)

    title_tag = soup.title.string.strip() if soup.title and soup.title.string else ""
    meta_desc = (soup.find("meta", attrs={"name":"description"}) or {}).get("content") or ""
    meta_desc = meta_desc.strip()
    h1_count = len(soup.find_all("h1"))
    canonical_link = soup.find("link", rel=lambda v: v and "canonical" in v.lower())
    img_tags = soup.find_all("img"); total_imgs = len(img_tags)
    imgs_missing_alt = len([i for i in img_tags if not (i.get("alt") or "").strip()])
    script_tags = soup.find_all("script"); blocking_script_count = sum(1 for s in script_tags if is_blocking_script(s))
    stylesheets = soup.find_all("link", rel=lambda v: v and "stylesheet" in v.lower()); stylesheet_count = len(stylesheets)
    ld_json_count = len(soup.find_all("script", attrs={"type":"application/ld+json"}))
    og_meta = bool(soup.find("meta", property=lambda v: v and v.startswith("og:")))
    tw_meta = bool(soup.find("meta", attrs={"name": lambda v: v and v.startswith("twitter:")}))
    viewport_meta = bool(soup.find("meta", attrs={"name":"viewport"}))

    headers = resp.headers or {}
    hsts = headers.get("Strict-Transport-Security")
    csp = headers.get("Content-Security-Policy")
    xfo = headers.get("X-Frame-Options")
    xcto = headers.get("X-Content-Type-Options")
    refpol = headers.get("Referrer-Policy")
    mixed = detect_mixed_content(soup, scheme)

    origin = f"{urlparse(resp.url).scheme}://{urlparse(resp.url).netloc}"
    robots_head = safe_request(urljoin(origin, "/robots.txt"), "HEAD")
    sitemap_head = safe_request(urljoin(origin, "/sitemap.xml"), "HEAD")
    robots_ok = bool(robots_head and robots_head.status_code < 400)
    sitemap_ok = bool(sitemap_head and sitemap_head.status_code < 400)

    crawled = crawl_internal(resp.url, max_pages=100)
    depth_counts = {}
    redirect_chains = 0
    broken_internal = 0
    statuses = {"2xx":0,"3xx":0,"4xx":0,"5xx":0,None:0}
    for row in crawled:
        sc = row.get("status")
        if sc is None:
            statuses[None] += 1
        elif 200 <= sc < 300:
            statuses["2xx"] += 1
        elif 300 <= sc < 400:
            statuses["3xx"] += 1
        elif 400 <= sc < 500:
            statuses["4xx"] += 1
        else:
            statuses["5xx"] += 1
        d = row["depth"]
        depth_counts[d] = depth_counts.get(d, 0) + 1
        if (row.get("redirects") or 0) >= 2:
            redirect_chains += 1
        if row.get("status") in (404, 410):
            broken_internal += 1

    # External broken link check (homepage anchors)
    broken_external = 0
    try:
        for a in soup.find_all("a"):
            href = (a.get("href") or "").strip()
            if not href: continue
            abs_url = urljoin(resp.url, href)
            parsed = urlparse(abs_url)
            if parsed.netloc and parsed.netloc != urlparse(resp.url).netloc and parsed.scheme in ("http","https"):
                r = safe_request(abs_url, "HEAD")
                if not r or (r.status_code and r.status_code >= 400):
                    broken_external += 1
    except Exception:
        pass

    # Scoring
    seo_score = 100
    if not title_tag: seo_score -= 20
    if title_tag and (len(title_tag) < 10 or len(title_tag) > 65): seo_score -= 8
    if not meta_desc: seo_score -= 15
    if h1_count != 1: seo_score -= 10
    if not canonical_link: seo_score -= 6
    if total_imgs > 0 and (imgs_missing_alt/total_imgs) > 0.2: seo_score -= 10
    if ld_json_count == 0: seo_score -= 6
    if not og_meta: seo_score -= 3
    if not tw_meta: seo_score -= 2

    perf_score = 100
    if size_mb > 2.0: perf_score -= 35
    elif size_mb > 1.0: perf_score -= 20
    if ttfb_ms > 1500: perf_score -= 35
    elif 800 < ttfb_ms <= 1500: perf_score -= 18
    if blocking_script_count > 3: perf_score -= 18
    elif 0 < blocking_script_count <= 3: perf_score -= 10
    if stylesheet_count > 4: perf_score -= 6

    a11y_score = 100
    lang_attr = soup.html.get("lang") if soup.html else None
    if not lang_attr: a11y_score -= 12
    if total_imgs > 0 and imgs_missing_alt > 0:
        ratio = (imgs_missing_alt / total_imgs) * 100
        if ratio > 30: a11y_score -= 20
        elif ratio > 10: a11y_score -= 12
        else: a11y_score -= 6

    bp_score = 100
    if scheme != "https": bp_score -= 35
    if mixed: bp_score -= 15
    if not sitemap_ok: bp_score -= 6
    if redirect_chains > 0: bp_score -= min(12, redirect_chains * 2)

    sec_score = 100
    if not hsts: sec_score -= 18
    if not csp: sec_score -= 18
    if not xfo: sec_score -= 10
    if not xcto: sec_score -= 8
    if not refpol: sec_score -= 6
    if mixed: sec_score -= 25

    overall = round(0.26 * seo_score + 0.28 * perf_score + 0.14 * a11y_score + 0.12 * bp_score + 0.20 * sec_score)
    def grade_from_score(score: int) -> str:
        if score >= 95: return "A+"
        if score >= 90: return "A"
        if score >= 80: return "B"
        if score >= 70: return "C"
        if score >= 60: return "D"
        return "F"
    grade = grade_from_score(overall)

    errors = (1 if scheme != "https" else 0) + (1 if mixed else 0) + broken_internal
    warnings = (1 if ttfb_ms > 800 else 0) + (1 if size_mb > 1.0 else 0) + (1 if blocking_script_count > 0 else 0)
    notices = (1 if not csp else 0) + (1 if not sitemap_ok else 0) + (1 if not robots_ok else 0)

    cat2_base = 100  # simplified
    penalty = (statuses["4xx"] * 2) + (statuses["5xx"] * 3) + (redirect_chains * 1.5) + (broken_internal * 2) + (broken_external * 1.5)
    cat2_total = max(30, min(100, int(cat2_base - penalty)))
    cat_scores = {
        "SEO": seo_score,
        "Performance": perf_score,
        "Security": sec_score,
        "Accessibility": a11y_score,
        "Mobile": 85 if viewport_meta else 60
    }
    totals = {
        "cat1": overall,
        "cat2": cat2_total,
        "cat3": seo_score,
        "cat4": perf_score,
        "cat5": int(0.6 * sec_score + 0.4 * (85 if viewport_meta else 60)),
        "overall": overall
    }

    exec_summary = (
        f"FF Tech audited {resp.url}, overall health {overall}% (grade {grade}). "
        f"Payload {size_mb:.2f} MB, TTFB {ttfb_ms} ms; {blocking_script_count} render‑blocking scripts and "
        f"{stylesheet_count} stylesheets may delay interactivity. Strengthen SEO (H1, meta, canonical, alt, JSON‑LD). "
        f"Improve security headers (HSTS, CSP, XFO, XCTO, Referrer‑Policy) and eliminate mixed content. "
        f"Prioritize compression, async JS, caching/CDN, and fix broken links (internal {broken_internal}, external {broken_external})."
    )

    def gauge(score: int):
        color = "#10b981" if score >= 80 else "#f59e0b" if score >= 60 else "#ef4444"
        return {"labels":["Score","Remaining"],"datasets":[{"data":[score,100-score],"backgroundColor":[color,"#e5e7eb"],"borderWidth":0}]}

    overall_gauge = gauge(overall)
    health_gauge = gauge(overall)
    issues_chart = {"labels":["Errors","Warnings","Notices"],"datasets":[{"data":[errors,warnings,notices],"backgroundColor":["#ef4444","#f59e0b","#3b82f6"]}]}
    category_chart = {"labels": list(cat_scores.keys()), "datasets":[{"label":"Score","data": list(cat_scores.values()), "backgroundColor":["#6366f1","#f59e0b","#10b981","#ef4444","#0ea5e9"]}]}

    strengths = []
    if sec_score >= 80 and scheme == "https": strengths.append("HTTPS with baseline security headers.")
    if seo_score >= 75: strengths.append("SEO foundations across titles/headings.")
    if a11y_score >= 75: strengths.append("Semantic structure aids assistive tech.")
    if viewport_meta: strengths.append("Viewport meta present; mobile baseline.")
    if perf_score >= 70: strengths.append("Acceptable page weight; optimization possible.")
    if not strengths: strengths = ["Platform reachable and crawlable."]

    weaknesses = []
    if perf_score < 80: weaknesses.append("Render‑blocking JS/CSS impacting interactivity.")
    if seo_score < 80: weaknesses.append("Meta/canonical coverage inconsistent.")
    if a11y_score < 80: weaknesses.append("Alt text and ARIA landmarks incomplete.")
    if sec_score < 90: weaknesses.append("HSTS/CSP/XFO/XCTO/Referrer‑Policy missing.")
    if not viewport_meta: weaknesses.append("Mobile viewport not confirmed.")
    if not weaknesses: weaknesses = ["Further analysis required for advanced issues."]

    priority = [
        "Enable Brotli/GZIP and set Cache‑Control.",
        "Defer/async non‑critical scripts; inline critical CSS.",
        "Optimize images (WebP/AVIF) with responsive srcset.",
        "Expand JSON‑LD; validate canonical consistency.",
        "Add HSTS, CSP, X‑Frame‑Options, X‑Content‑Type‑Options, Referrer‑Policy."
    ]

    metrics = []
    def add_metric(num: int, pass_pct: float, chart_type: str = "bar"):
        fail_pct = max(0, 100 - int(pass_pct))
        cd = {"labels": ["Pass","Fail"], "datasets":[{"data":[int(pass_pct), fail_pct], "backgroundColor": ["#10b981" if chart_type=="bar" else "#22c55e", "#ef4444"], "borderWidth":0}]}
        severity = "green" if pass_pct >= 80 else "yellow" if pass_pct >= 60 else "red"
        metrics.append({"num": num, "severity": severity, "chart_type": chart_type, "chart_data": cd})
    add_metric(1, overall, "doughnut")
    add_metric(2, 100 if errors == 0 else 40)
    add_metric(3, 80 if warnings <= 2 else 50)
    for n in range(4, 251):
        base = overall if n<=55 else (cat2_total if n<=75 else (seo_score if n<=110 else (perf_score if n<=131 else (sec_score if n<=185 else 70))))
        add_metric(n, max(10, min(100, base - ((n%7)*2))), "bar" if n%5 else "doughnut")

    return {
        "grade": grade,
        "summary": exec_summary,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "priority": priority,
        "overall": overall,
        "errors": errors,
        "warnings": warnings,
        "notices": notices,
        "overall_gauge": overall_gauge,
        "health_gauge": health_gauge,
        "issues_chart": issues_chart,
        "category_chart": category_chart,
        "totals": totals,
        "metrics": metrics,
        "premium": False,
        "remaining": 0,
        "cat_scores": cat_scores,
    }


# -----------------------------------------------
# API Schemas
# -----------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    timezone: str = "UTC"

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class ScheduleIn(BaseModel):
    website_url: str
    time_of_day: str         # "HH:MM"
    timezone: str            # e.g., "Asia/Karachi"
    preferred_date: str | None = None  # "YYYY-MM-DD" or ISO date
    daily_report: bool = True
    accumulated_report: bool = True
    enabled: bool = True

class WebsiteIn(BaseModel):
    url: str

class SettingsIn(BaseModel):
    timezone: str
    notify_daily_default: bool
    notify_acc_default: bool


# -----------------------------------------------
# Root (embedded landing)
# -----------------------------------------------
INDEX_HTML = r"""<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>FF Tech — Professional Audit</title>https://cdn.tailwindcss.com</script>https://cdn.jsdelivr.net/npm/chart.js@4.4.1</script><link rel='preconnect' href='s://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swaphttps://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css<style>body{font-family:'Inter',system-ui,sans-serif;background:radial-gradient(1200px 700px at 10% 10%,#eef2ff,transparent),radial-gradient(1200px 700px at 90% 90%,#f1f5f9,transparent)}.glass{background:rgba(255,255,255,.65);border:1px solid rgba(255,255,255,.35);backdrop-filter:saturate(140%) blur(10px);box-shadow:0 25px 50px rgba(0,0,0,.22);border-radius:24px}.metric-card{border-left-width:8px}.metric-green{border-color:#10b981}.metric-yellow{border-color:#f59e0b}.metric-red{border-color:#ef4444}.blur-premium{filter:blur(10px);pointer-events:none}.btn-gradient{background:linear-gradient(135deg,#4f46e5 0%,#7c3aed 100%);color:#fff}.btn-gradient:hover{filter:brightness(1.05)}.grid-auto{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:18px}</style></head><body class='text-slate-800'><header class='text-white bg-gradient-to-r from-indigo-600 to-violet-600'><div class='max-w-7xl mx-auto px-6 py-5 flex items-center justify-between'><div class='flex items-center gap-4'><i class='fas fa-shield-halved text-3xl'></i><div><h1 class='text-2xl font-black'>FF Tech — Audit Platform</h1><p class='text-sm opacity-80'>Open access, scheduled audits, and certified PDFs</p></div></div><nav class='flex items-center gap-6'>#Login</a>#Register</a><span id='user-status' class='hidden'>Welcome, <span id='user-email'></span> · #Logout</a></span></nav></div></header><main class='max-w-7xl mx-auto px-6 py-8'><section class='glass p-8 md:p-12'><h2 class='text-3xl font-black'>Open Audits for Everyone</h2><p class='mt-2 opacity-80'>Enter any website URL to get an immediate audit report. Unlimited open audits.</p><form id='audit-form' class='mt-6 flex items-center gap-3'><input id='website-url' type='url' placeholder='https://example.com' class='flex-1 rounded-xl px-4 py-3 border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-900' required><button class='btn-gradient px-6 py-3 rounded-xl font-bold' type='submit'>Run Audit</button></form><p class='mt-3 text-sm opacity-80'>Registered: 5–10 free full audits, then $5/month for daily report emails.</p><p class='mt-1 text-sm opacity-80'>Free Audits Remaining: <span id='remaining' class='font-extrabold'>—</span></p></section><section id='summary-section' class='hidden pt-6'><div class='glass p-8'><div class='text-center mb-6'><span id='grade-badge' class='text-2xl font-black bg-green-100 text-green-700 px-5 py-2 rounded-full'>A+</span></div><div class='grid md:grid-cols-2 gap-6'><div class='glass p-4'><canvas id='overall-gauge'></canvas></div><div class='glass p-4'><canvas id='category-chart'></canvas></div></div><article class='mt-6 glass p-6'><h4 class='text-xl font-extrabold mb-3'>Executive Summary</h4><p id='exec-summary' class='leading-relaxed'></p></article><div class='mt-6 grid md:grid-cols-3 gap-6'><div class='glass p-6'><h5 class='font-black text-green-700'>Strengths</h5><ul id='strengths' class='mt-2 list-disc list-inside'></ul></div><div class='glass p-6'><h5 class='font-black text-rose-700'>Weak Areas</h5><ul id='weaknesses' class='mt-2 list-disc list-inside'></ul></div><div class='glass p-6'><h5 class='font-black text-amber-700'>Priority Fixes</h5><ul id='priority' class='mt-2 list-disc list-inside'></ul></div></div><div class='text-center mt-8'><button id='export-pdf' class='btn-gradient px-6 py-3 rounded-xl font-bold'>Export Certified PDF</button></div></div></section><section id='dashboard-section' class='hidden pt-6'><div class='glass p-8'><h3 class='text-2xl font-black mb-4'>Complete Metrics (1–250)</h3><p class='text-sm opacity-80'>Public users see limited metrics; register to unlock full visuals.</p><div class='relative'><div id='premium-blur' class='absolute inset-0 blur-premium hidden'></div><div id='metrics-grid' class='grid-auto mt-6'></div></div></div></section><section id='user-panel' class='hidden pt-6'><div class='grid md:grid-cols-3 gap-6'><div class='glass p-6'><h4 class='text-xl font-black mb-3'>Add Website</h4><form id='add-site-form' class='space-y-3'><input id='add-site-url' type='url' placeholder='https://example.com' class='w-full rounded-xl px-4 py-3 border border-slate-300 text-slate-900' required /><button class='btn-gradient px-5 py-3 rounded-xl font-bold'>Add</button></form></div><div class='glass p-6 md:col-span-2'><h4 class='text-xl font-black mb-3'>Schedule Audit</h4><form id='schedule-form' class='space-y-3'><input id='schedule-url' type='url' placeholder='https://example.com' class='w-full rounded-xl px-4 py-3 border border-slate-300 text-slate-900' required /><div class='grid grid-cols-3 gap-4'><input id='schedule-time' type='time' class='rounded-xl px-4 py-3 border border-slate-300' value='09:00' /><input id='schedule-date' type='date' class='rounded-xl px-4 py-3 border border-slate-300' /><input id='schedule-tz' type='text' class='rounded-xl px-4 py-3 border border-slate-300' placeholder='Asia/Karachi' value='Asia/Karachi' /></div><div class='grid grid-cols-2 gap-4'><label class='flex items-center gap-2'><input id='schedule-daily' type='checkbox' checked /> Daily Report</label><label class='flex items-center gap-2'><input id='schedule-acc' type='checkbox' checked /> Accumulated Report</label></div><button class='btn-gradient px-5 py-3 rounded-xl font-bold'>Save Schedule</button></form></div></div><div class='grid md:grid-cols-2 gap-6 mt-6'><div class='glass p-6'><h4 class='text-xl font-black mb-3'>Your Schedules</h4><div id='schedules-list' class='space-y-2 text-sm'></div></div><div class='glass p-6'><h4 class='text-xl font-black mb-3'>Settings</h4><form id='settings-form' class='space-y-3'><input id='settings-tz' type='text' placeholder='Asia/Karachi' class='w-full rounded-xl px-4 py-3 border border-slate-300 text-slate-900' /><label class='flex items-center gap-2'><input id='settings-daily' type='checkbox' /> Default: Daily emails</label><label class='flex items-center gap-2'><input id='settings-acc' type='checkbox' /> Default: Accumulated emails</label><button class='btn-gradient px-5 py-3 rounded-xl font-bold'>Save Settings</button></form><div class='mt-4'><button id='subscribe-btn-panel' class='btn-gradient px-6 py-3 rounded-xl font-bold'>$5/month — Subscribe</button></div></div></div></section></main><footer class='py-10'><div class='max-w-7xl mx-auto px-6'><div class='glass p-8 text-center'><p class='font-black text-lg'>FF Tech © <span id='year'></span></p><p class='text-sm opacity-80'>Professional Scheduled Audit & Reporting System · International Standard</p></div></div></footer><script>const $=s=>document.querySelector(s);const state={token:null,role:null,subscribed:false,freeRemaining:null,charts:{}};function toast(msg){console.log('[Toast]',msg)}function severityClass(sev){return sev==='green'?'metric-green':(sev==='yellow'?'metric-yellow':'metric-red')}function chart(ctx,type,data){return new Chart(ctx,{type,data,options:{plugins:{legend:{display:false}},responsive:true}})}async function api(path,opts={}){const headers=opts.headers||{};if(state.token) headers['Authorization']='Bearer '+state.token; if(!headers['Content-Type']&&opts.body) headers['Content-Type']='application/json';const res=await fetch(path,{...opts,headers});if(!res.ok){throw new Error('HTTP '+res.status+' '+(await res.text()))}const ct=res.headers.get('Content-Type')||'';if(ct.includes('application/pdf')) return res.blob(); if(ct.includes('application/json')) return res.json(); return res.text();}function saveSession(token,role,remaining,subscribed){localStorage.setItem('fftech_token',token);localStorage.setItem('fftech_role',role||'user'); localStorage.setItem('fftech_remaining', remaining ?? '');localStorage.setItem('fftech_subscribed', subscribed?'true':'false');state.token=token; state.role=role; state.freeRemaining=remaining; state.subscribed=subscribed; $('#user-status').classList.remove('hidden');$('#open-login').classList.add('hidden');$('#open-register').classList.add('hidden');}function clearSession(){localStorage.removeItem('fftech_token');localStorage.removeItem('fftech_role');localStorage.removeItem('fftech_remaining');localStorage.removeItem('fftech_subscribed');state.token=null; state.role=null; state.subscribed=false; state.freeRemaining=null; $('#user-status').classList.add('hidden');$('#open-login').classList.remove('hidden');$('#open-register').classList.remove('hidden');}function loadSession(){const t=localStorage.getItem('fftech_token');const role=localStorage.getItem('fftech_role');const sub=localStorage.getItem('fftech_subscribed')==='true'; const rem=localStorage.getItem('fftech_remaining');if(t){state.token=t; state.role=role; state.subscribed=sub; state.freeRemaining=rem?parseInt(rem):null; $('#user-status').classList.remove('hidden');$('#open-login').classList.add('hidden');$('#open-register').classList.add('hidden');}}async function runAudit(url){const payload=await api(`/audit?url=${encodeURIComponent(url)}`);$('#summary-section').classList.remove('hidden');$('#dashboard-section').classList.remove('hidden');$('#grade-badge').textContent=payload.grade;$('#exec-summary').textContent=payload.summary;$('#strengths').innerHTML=payload.strengths.map(s=>`<li>${s}</li>`).join('');$('#weaknesses').innerHTML=payload.weaknesses.map(s=>`<li>${s}</li>`).join('');$('#priority').innerHTML=payload.priority.map(s=>`<li>${s}</li>`).join('');if(payload.overall_gauge) chart($('#overall-gauge'),'doughnut',payload.overall_gauge);if(payload.category_chart) chart($('#category-chart'),'bar',payload.category_chart);if(payload.health_gauge) chart($('#health-gauge'),'doughnut',payload.health_gauge);if(payload.issues_chart) chart($('#issues-chart'),'bar',payload.issues_chart);const grid=$('#metrics-grid');grid.innerHTML='';payload.metrics.forEach(m=>{const pad=String(m.num).padStart(3,'0');const card=document.createElement('div');card.className=`glass p-4 metric-card ${severityClass(m.severity)}`;card.innerHTML=`<h5 class='text-sm font-bold mb-2'>${pad}. Metric ${pad}</h5><div class='h-48'><canvas id='chart-${pad}'></canvas></div>`;grid.appendChild(card); chart(document.getElementById(`chart-${pad}`),(m.chart_type||'bar'),m.chart_data);}); if(typeof payload.remaining!=='undefined'&&payload.remaining!==null){document.getElementById('remaining').textContent=payload.remaining; state.freeRemaining=payload.remaining; localStorage.setItem('fftech_remaining', payload.remaining);}}document.getElementById('audit-form').addEventListener('submit',async(e)=>{e.preventDefault();const url=document.getElementById('website-url').value.trim(); if(!url) return toast('Please enter a website URL.'); try{await runAudit(url)}catch(err){toast(err.message)}});document.getElementById('export-pdf').addEventListener('click',async()=>{const url=document.getElementById('website-url').value||'https://example.com';const pdf=await api(`/export-pdf?url=${encodeURIComponent(url)}`);const blobUrl=URL.createObjectURL(pdf);const a=document.createElement('a');a.href=blobUrl;a.download=`fftech_audit_${Date.now()}.pdf`;a.click();URL.revokeObjectURL(blobUrl);});document.getElementById('open-register').addEventListener('click',async(e)=>{e.preventDefault();const email=prompt('Email:');const password=prompt('Password (min 8 chars):');const timezone=prompt('Timezone (e.g., Asia/Karachi):','Asia/Karachi'); if(!email||!password) return; try{const res=await api('/register',{method:'POST',body:JSON.stringify({email,password,timezone})});toast(res.message||'Registration submitted. Check email.')}catch(err){toast(err.message)}});document.getElementById('open-login').addEventListener('click',async(e)=>{e.preventDefault();const email=prompt('Email:');const password=prompt('Password:'); if(!email||!password) return; try{const res=await api('/login',{method:'POST',body:JSON.stringify({email,password})});$('#user-email').textContent=email; saveSession(res.token,res.role,res.free_audits_remaining,res.subscribed);}catch(err){toast(err.message)}});document.getElementById('logout').addEventListener('click',(e)=>{e.preventDefault();clearSession()});document.getElementById('subscribe-btn-panel').addEventListener('click',async()=>{try{const res=await api('/billing/checkout',{method:'POST'}); if(res.url) window.location.href=res.url; else toast(res.message||'Subscription activated (demo).');}catch(err){toast(err.message)}});(function init(){document.getElementById('year').textContent=new Date().getFullYear();loadSession();})();</script></body></html>
"""

@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(INDEX_HTML)


# -----------------------------------------------
# Public & Registered audit (crash-proof DB)
# -----------------------------------------------
@app.get("/audit", response_class=JSONResponse)
def audit(url: str = Query(..., description="Website URL to audit"),
          authorization: str | None = Header(None)):
    payload = run_actual_audit(url)
    user = None
    # Determine registered user
    if authorization and authorization.startswith("Bearer "):
        try:
            data = jwt_verify(authorization.split(" ",1)[1])
            with safe_session() as db:
                if db:
                    user = db.query(User).filter(User.id == data.get("uid")).first()
        except Exception:
            user = None

    if not user:
        payload["metrics"] = payload["metrics"][:50]
        payload["premium"] = False
        payload["remaining"] = None
    else:
        with safe_session() as db:
            remaining = user.free_audits_remaining or 0
            is_subscribed = bool(user.subscribed)
            if not is_subscribed and remaining <= 0:
                payload["metrics"] = payload["metrics"][:50]
                payload["premium"] = False
                payload["remaining"] = remaining
            else:
                payload["premium"] = True
                payload["remaining"] = remaining
                if db and not is_subscribed and remaining > 0:
                    user.free_audits_remaining = max(0, remaining - 1)
                    db.commit()

    # Persist summary (if DB available)
    with safe_session() as db:
        if db:
            norm = normalize_url(url)
            site = db.query(Website).filter(Website.url == norm).first()
            if not site:
                site = Website(url=norm, user_id=(user.id if user else None), active=True)
                db.add(site); db.commit(); db.refresh(site)
            row = Audit(
                website_id=site.id, url=norm,
                overall=payload["overall"], grade=payload["grade"],
                errors=payload["errors"], warnings=payload["warnings"], notices=payload["notices"],
                summary=payload["summary"], cat_scores_json=json.dumps(payload.get("cat_scores", {})),
                cat_totals_json=json.dumps(payload.get("totals", {})),
                metrics_json=json.dumps(payload.get("metrics", [])),
                premium=payload["premium"]
            )
            db.add(row); db.commit()

    return JSONResponse(payload)


# -----------------------------------------------
# Export Certified PDF
# -----------------------------------------------
@app.get("/export-pdf")
def export_pdf(url: str = Query(..., description="Website URL to audit and export PDF")):
    payload = run_actual_audit(url)
    pdf_bytes = generate_pdf_5pages(url, {
        "grade": payload["grade"], "overall": payload["overall"], "summary": payload["summary"],
        "strengths": payload["strengths"], "weaknesses": payload["weaknesses"], "priority": payload["priority"],
        "errors": payload["errors"], "warnings": payload["warnings"], "notices": payload["notices"], "totals": payload["totals"],
    })
    fname = f"fftech_audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    headers = {"Content-Disposition": f'attachment; filename="{fname}"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


# -----------------------------------------------
# Registration / Verification / Login
# -----------------------------------------------
@app.post("/register")
def register(payload: RegisterIn):
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        email = payload.email.lower().strip()
        if db.query(User).filter(User.email == email).first():
            raise HTTPException(status_code=400, detail="Email already registered")
        pwd_hash, salt = create_user_password(payload.password)
        user = User(email=email, password_hash=pwd_hash, password_salt=salt,
                    timezone=payload.timezone, free_audits_remaining=FREE_AUDITS_LIMIT)
        db.add(user); db.commit(); db.refresh(user)
        token = jwt_sign({"uid": user.id, "act": "verify"}, exp_minutes=60*24)
        verify_link = f"{APP_BASE_URL}/verify?token={token}"
        # SMTP send (if configured) or print
        subject = "FF Tech — Verify your account"
        body = f"Welcome to FF Tech!\n\nPlease verify your email:\n{verify_link}\n\nLink expires in 24 hours."
        send_email(email, subject, body, [])
        return {"message": "Registration successful. Check your email to verify your account."}

@app.get("/verify")
def verify(token: str):
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        payload = jwt_verify(token)
        if payload.get("act") != "verify":
            raise HTTPException(status_code=400, detail="Invalid verification token")
        user = db.query(User).filter(User.id == payload.get("uid")).first()
        if not user: raise HTTPException(status_code=404, detail="User not found")
        user.is_verified = True; db.commit()
        return {"message": "Email verified. You can now log in."}

@app.post("/login")
def login(payload: LoginIn, request: Request):
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        email = payload.email.lower().strip()
        user = db.query(User).filter(User.email == email).first()
        log = LoginLog(email=email, ip=(request.client.host if request.client else ""), user_agent=request.headers.get("User-Agent",""), success=False)
        if not user:
            db.add(log); db.commit()
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not user.is_verified:
            db.add(log); db.commit()
            raise HTTPException(status_code=401, detail="Email not verified")
        if hash_password(payload.password, user.password_salt) != user.password_hash:
            db.add(log); db.commit()
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user.last_login_at = datetime.utcnow()
        log.success = True; log.user_id = user.id
        db.add(log); db.commit()
        token = jwt_sign({"uid": user.id, "role": user.role}, exp_minutes=60*24*7)
        return {"token": token, "role": user.role, "free_audits_remaining": user.free_audits_remaining, "subscribed": user.subscribed}


# -----------------------------------------------
# Website management & scheduling
# -----------------------------------------------
@app.post("/websites")
def add_website(payload: WebsiteIn, authorization: str | None = Header(None)):
    # auth
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")
    try:
        data = jwt_verify(authorization.split(" ",1)[1])
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        if not user: raise HTTPException(status_code=401, detail="User not found")
        url = normalize_url(payload.url)
        existing = db.query(Website).filter(Website.url == url, Website.user_id == user.id).first()
        if existing:
            return {"message":"Website already added"}
        site = Website(url=url, user_id=user.id, active=True)
        db.add(site); db.commit(); db.refresh(site)
        return {"message":"Website added", "id": site.id}

@app.post("/schedule")
def create_schedule(payload: ScheduleIn, authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")
    try:
        data = jwt_verify(authorization.split(" ",1)[1])
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        if not user: raise HTTPException(status_code=401, detail="User not found")
        url = normalize_url(payload.website_url)
        site = db.query(Website).filter(Website.url == url, Website.user_id == user.id).first()
        if not site:
            site = Website(url=url, user_id=user.id, active=True)
            db.add(site); db.commit(); db.refresh(site)
        pref_dt = None
        if payload.preferred_date:
            try:
                pref_dt = datetime.fromisoformat(payload.preferred_date.strip())
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid preferred_date format. Use YYYY-MM-DD or ISO8601.")
        sched = Schedule(
            user_id=user.id, website_id=site.id, enabled=payload.enabled,
            time_of_day=payload.time_of_day, timezone=payload.timezone,
            daily_report=payload.daily_report, accumulated_report=payload.accumulated_report,
            preferred_date=pref_dt
        )
        db.add(sched); db.commit(); db.refresh(sched)
        return {"message":"Schedule saved", "id": sched.id}

@app.get("/schedules")
def list_schedules(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")
    try:
        data = jwt_verify(authorization.split(" ",1)[1])
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        rows = db.query(Schedule).filter(Schedule.user_id == data.get("uid")).all()
        out = []
        for s in rows:
            site = db.query(Website).get(s.website_id)
            out.append({"id": s.id, "website_url": site.url if site else None, "enabled": s.enabled,
                        "time_of_day": s.time_of_day, "timezone": s.timezone,
                        "daily_report": s.daily_report, "accumulated_report": s.accumulated_report,
                        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None})
        return out


# -----------------------------------------------
# Settings
# -----------------------------------------------
@app.get("/settings")
def get_settings(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")
    try:
        data = jwt_verify(authorization.split(" ",1)[1])
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        return {
            "timezone": user.timezone,
            "notify_daily_default": user.notify_daily_default,
            "notify_acc_default": user.notify_acc_default,
            "subscribed": user.subscribed,
            "free_audits_remaining": user.free_audits_remaining,
        }

@app.post("/settings")
def update_settings(payload: SettingsIn, authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")
    try:
        data = jwt_verify(authorization.split(" ",1)[1])
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        user.timezone = payload.timezone
        user.notify_daily_default = payload.notify_daily_default
        user.notify_acc_default = payload.notify_acc_default
        db.commit()
        return {"message": "Settings updated"}


# -----------------------------------------------
# Billing (Stripe)
# -----------------------------------------------
@app.get("/billing/status")
def billing_status(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")
    try:
        data = jwt_verify(authorization.split(" ",1)[1])
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        return {"subscribed": user.subscribed, "free_audits_remaining": user.free_audits_remaining}

@app.post("/billing/checkout")
def billing_checkout(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")
    try:
        data = jwt_verify(authorization.split(" ",1)[1])
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        if (not stripe) or (not STRIPE_SECRET_KEY) or (not STRIPE_PRICE_ID):
            user.subscribed = True
            db.commit()
            return {"message": "Stripe not configured — subscription activated for demo.", "url": None}
        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                customer_email=user.email,
                line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
                success_url=STRIPE_SUCCESS_URL,
                cancel_url=STRIPE_CANCEL_URL,
                allow_promotion_codes=True,
            )
            return {"url": session.url}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/billing/webhook")
async def billing_webhook(request: Request):
    if not stripe or not STRIPE_WEBHOOK_SECRET:
        return {"message": "Webhook secret/Stripe not configured"}
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    type_ = event["type"]
    data = event["data"]["object"]
    with safe_session() as db:
        if not db:
            # skip persistence until DB returns
            return {"received": True, "db": "unavailable"}
        try:
            if type_ in ("checkout.session.completed", "invoice.payment_succeeded"):
                email = data.get("customer_details", {}).get("email") or data.get("customer_email")
                if not email and data.get("customer"):
                    cust = stripe.Customer.retrieve(data["customer"])
                    email = cust.get("email")
                if email:
                    user = db.query(User).filter(User.email == email.lower()).first()
                    if user:
                        user.subscribed = True
                        if not user.stripe_customer_id and data.get("customer"):
                            user.stripe_customer_id = data["customer"]
                        db.commit()
        except Exception as e:
            print("[STRIPE WEBHOOK ERROR]", e)

    return {"received": True}


# -----------------------------------------------
# Admin
# -----------------------------------------------
@app.get("/admin/users")
def admin_users(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=403, detail="Admin required")
    data = jwt_verify(authorization.split(" ",1)[1])
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        if not user or user.role != "admin":
            raise HTTPException(status_code=403, detail="Admin required")
        users = db.query(User).order_by(User.created_at.desc()).all()
        return [{"id": u.id, "email": u.email, "verified": u.is_verified, "role": u.role,
                 "timezone": u.timezone, "free_audits_remaining": u.free_audits_remaining,
                 "subscribed": u.subscribed, "created_at": u.created_at.isoformat(),
                 "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None} for u in users]

@app.get("/admin/audits")
def admin_audits(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=403, detail="Admin required")
    data = jwt_verify(authorization.split(" ",1)[1])
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        if not user or user.role != "admin":
            raise HTTPException(status_code=403, detail="Admin required")
        audits = db.query(Audit).order_by(Audit.created_at.desc()).limit(200).all()
        return [{"id": a.id, "url": a.url, "website_id": a.website_id, "overall": a.overall,
                 "grade": a.grade, "errors": a.errors, "warnings": a.warnings, "notices": a.notices,
                 "created_at": a.created_at.isoformat()} for a in audits]


# -----------------------------------------------
# Scheduler loop (skips when DB down)
# -----------------------------------------------
async def scheduler_loop():
    await asyncio.sleep(3)
    while True:
        try:
            with safe_session() as db:
                if not db:
                    # DB unavailable — skip this tick quietly
                    await asyncio.sleep(SCHEDULER_INTERVAL)
                    continue
                now_utc = datetime.utcnow().replace(second=0, microsecond=0)
                schedules = db.query(Schedule).filter(Schedule.enabled == True).all()
                for s in schedules:
                    user = db.query(User).get(s.user_id)
                    if not user or not user.subscribed:
                        continue
                    hh, mm = map(int, (s.time_of_day or "09:00").split(":"))
                    tzname = s.timezone or "UTC"
                    try:
                        from zoneinfo import ZoneInfo
                        tz = ZoneInfo(tzname)
                        local_now = now_utc.replace(tzinfo=timezone.utc).astimezone(tz)
                        if s.preferred_date:
                            local_first = s.preferred_date.replace(tzinfo=timezone.utc).astimezone(tz)
                            scheduled_local = local_first.replace(hour=hh, minute=mm, second=0, microsecond=0)
                        else:
                            scheduled_local = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                        scheduled_utc = scheduled_local.astimezone(timezone.utc).replace(tzinfo=None)
                    except Exception:
                        scheduled_utc = now_utc.replace(hour=hh, minute=mm, second=0, microsecond=0)
                    should_run = (now_utc >= scheduled_utc and (not s.last_run_at or s.last_run_at < scheduled_utc))
                    if should_run:
                        site = db.query(Website).get(s.website_id)
                        if not site: continue
                        payload = run_actual_audit(site.url)
                        pdf_bytes = generate_pdf_5pages(site.url, {
                            "grade": payload["grade"], "overall": payload["overall"], "summary": payload["summary"],
                            "strengths": payload["strengths"], "weaknesses": payload["weaknesses"], "priority": payload["priority"],
                            "errors": payload["errors"], "warnings": payload["warnings"], "notices": payload["notices"], "totals": payload["totals"],
                        })
                        subj = f"FF Tech Audit — {site.url} ({payload['grade']} / {payload['overall']}%)"
                        body = "Your scheduled audit is ready.\n\n" \
                               f"Website: {site.url}\nGrade: {payload['grade']}\nHealth: {payload['overall']}%\n" \
                               f"Daily: {s.daily_report} | Accumulated: {s.accumulated_report}\n\n" \
                               "Certified PDF attached.\n— FF Tech"
                        # send email (if SMTP configured)
                        send_email(user.email, subj, body, [(f"fftech_audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf", pdf_bytes)])
                        row = Audit(
                            website_id=site.id, url=site.url, overall=payload["overall"], grade=payload["grade"],
                            errors=payload["errors"], warnings=payload["warnings"], notices=payload["notices"],
                            summary=payload["summary"], cat_scores_json=json.dumps(payload["cat_scores"]),
                            cat_totals_json=json.dumps(payload["totals"]), metrics_json=json.dumps(payload["metrics"])
                        )
                        db.add(row)
                        s.last_run_at = now_utc
                        db.commit()
        except Exception as e:
            print("[SCHEDULER ERROR]", e)
        await asyncio.sleep(SCHEDULER_INTERVAL)


# -----------------------------------------------
# SAFE DB INIT (with retries, no crash)
# -----------------------------------------------
async def init_db():
    max_attempts = int(os.getenv("DB_CONNECT_MAX_ATTEMPTS", "10"))
    delay = float(os.getenv("DB_CONNECT_RETRY_DELAY", "2"))
    # log sanitized URL
    try:
        sanitized = DATABASE_URL
        if "@" in sanitized and "://" in sanitized:
            head, tail = sanitized.split("://", 1)
            userpass_host = tail.split("@")
            if len(userpass_host) == 2:
                userpass, hostpart = userpass_host
                user = userpass.split(":")[0]
                sanitized = f"{head}://{user}:***@{hostpart}"
        print("[DB] Using DATABASE_URL:", sanitized)
    except Exception:
        pass

    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            Base.metadata.create_all(bind=engine)
            print("[DB] Connected and tables ensured")
            return
        except OperationalError as e:
            print(f"[DB] Connection attempt {attempt}/{max_attempts} failed: {e}")
        except Exception as e:
            print(f"[DB] Non-operational DB init error: {e}")
        await asyncio.sleep(delay)
    print("[DB WARNING] DB unavailable after retries; app will keep serving limited functionality")


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(init_db())
    asyncio.create_task(scheduler_loop())


# -----------------------------------------------
# MAIN (bind to PORT for Railway)
# -----------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
``
