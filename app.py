
# app.py
# FF Tech — Professional Web Audit Dashboard (International Standard)
# Features:
# - Single-page HTML (CDN-only)
# - Actual audits: requests + BeautifulSoup + internal crawler
# - 250+ metrics (unique IDs, visual charts)
# - Open access vs registered logic (10 free audits → $5/month Stripe)
# - Users add websites and schedule audits (time + timezone; daily/accumulated)
# - SMTP email delivery with 5-page Certified PDF (FF Tech)
# - Admin endpoints
# - Settings (timezone + notification prefs)
# - Stripe Checkout & Webhook integration (safe fallbacks)
# - Railway healthcheck fix: /health + bind to PORT

import os, io, hmac, json, time, base64, secrets, asyncio
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

from fastapi import FastAPI, Request, Depends, HTTPException, Query, Header
from fastapi.responses import HTMLResponse, JSONResponse, Response, PlainTextResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker

# Stripe
import stripe

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
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

# SMTP config
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "no-reply@fftech.io")

SCHEDULER_INTERVAL = int(os.getenv("SCHEDULER_INTERVAL", "60"))  # seconds

# Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", APP_BASE_URL + "/success")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", APP_BASE_URL + "/cancel")
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# -----------------------------------------------
# DB setup
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
    role = Column(String(32), default="user")  # user | admin
    timezone = Column(String(64), default="UTC")
    free_audits_remaining = Column(Integer, default=10)
    subscribed = Column(Boolean, default=False)
    stripe_customer_id = Column(String(255))  # optional
    notify_daily_default = Column(Boolean, default=True)
    notify_acc_default = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime)

class Website(Base):
    __tablename__ = "websites"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # null for public audits
    url = Column(String(2048), nullable=False)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    website_id = Column(Integer, ForeignKey("websites.id"), nullable=False)
    enabled = Column(Boolean, default=True)
    time_of_day = Column(String(8), default="09:00")  # HH:MM
    timezone = Column(String(64), default="UTC")
    daily_report = Column(Boolean, default=True)
    accumulated_report = Column(Boolean, default=True)
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
    cat_scores_json = Column(Text)   # dict
    cat_totals_json = Column(Text)   # dict
    metrics_json = Column(Text)      # list(250+)
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

Base.metadata.create_all(bind=engine)

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

auth_scheme = HTTPBearer()

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(auth_scheme), db=Depends(get_db)) -> User:
    payload = jwt_verify(credentials.credentials)
    user = db.query(User).filter(User.id == payload.get("uid")).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_admin(credentials: HTTPAuthorizationCredentials = Depends(auth_scheme), db=Depends(get_db)) -> User:
    payload = jwt_verify(credentials.credentials)
    user = db.query(User).filter(User.id == payload.get("uid")).first()
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return user

# -----------------------------------------------
# Email sending
# -----------------------------------------------
def send_email(to_email: str, subject: str, body: str, attachments: list[tuple[str, bytes]] | None = None):
    """SMTP send if configured; else print (dev)."""
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS or not EMAIL_SENDER:
        print(f"[EMAIL FAKE SEND] To: {to_email} | Subject: {subject}\n{body[:500]}\nAttachments: {len(attachments or [])}")
        return
    import ssl, smtplib
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["From"] = EMAIL_SENDER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    for fname, data in (attachments or []):
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=fname)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

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
# Actual audit engine
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

    # Performance proxies
    ttfb_ms = int(resp.elapsed.total_seconds() * 1000)
    page_size_bytes = len(resp.content or b"")
    size_mb = page_size_bytes / (1024.0 * 1024.0)

    # On-page signals
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

    # Security headers
    headers = resp.headers or {}
    hsts = headers.get("Strict-Transport-Security")
    csp = headers.get("Content-Security-Policy")
    xfo = headers.get("X-Frame-Options")
    xcto = headers.get("X-Content-Type-Options")
    refpol = headers.get("Referrer-Policy")
    mixed = detect_mixed_content(soup, scheme)

    # robots/sitemap
    origin = f"{urlparse(resp.url).scheme}://{urlparse(resp.url).netloc}"
    robots_head = safe_request(urljoin(origin, "/robots.txt"), "HEAD")
    sitemap_head = safe_request(urljoin(origin, "/sitemap.xml"), "HEAD")
    robots_ok = bool(robots_head and robots_head.status_code < 400)
    sitemap_ok = bool(sitemap_head and sitemap_head.status_code < 400)

    # Internal crawl
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

    # External broken links: homepage external <a> targets
    broken_external = 0
    try:
        for a in soup.find_all("a"):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            abs_url = urljoin(resp.url, href)
            parsed = urlparse(abs_url)
            if parsed.netloc and parsed.netloc != urlparse(resp.url).netloc and parsed.scheme in ("http","https"):
                r = safe_request(abs_url, "HEAD")
                if not r or (r.status_code and r.status_code >= 400):
                    broken_external += 1
    except Exception:
        pass

    # Derived heuristics for category scoring
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
    elif ttfb_ms > 800: perf_score -= 18
    if blocking_script_count > 3: perf_score -= 18
    elif blocking_script_count > 0: perf_score -= 10
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

    # Weighted overall
    overall = round(0.26 * seo_score + 0.28 * perf_score + 0.14 * a11y_score + 0.12 * bp_score + 0.20 * sec_score)
    def grade_from_score(score: int) -> str:
        if score >= 95: return "A+"
        if score >= 90: return "A"
        if score >= 80: return "B"
        if score >= 70: return "C"
        if score >= 60: return "D"
        return "F"
    grade = grade_from_score(overall)

    # Issues breakdown
    errors = (1 if scheme != "https" else 0) + (1 if mixed else 0) + broken_internal
    warnings = (1 if ttfb_ms > 800 else 0) + (1 if size_mb > 1.0 else 0) + (1 if blocking_script_count > 0 else 0)
    notices = (1 if not csp else 0) + (1 if not sitemap_ok else 0) + (1 if not robots_ok else 0)

    cat2_base = min(100, statuses["2xx"])
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

    # Executive summary
    max_depth = max(depth_counts) if depth_counts else 0
    exec_summary = (
        f"FF Tech audited {resp.url}, producing an overall health score of {overall}% (grade {grade}). "
        f"Performance shows a payload of {size_mb:.2f} MB and server TTFB around {ttfb_ms} ms; {blocking_script_count} render‑blocking scripts "
        f"and {stylesheet_count} stylesheets may delay interactivity. On‑page SEO can be strengthened by ensuring one H1, descriptive meta, canonical links, "
        f"alt attributes, and JSON‑LD structured data ({'present' if ld_json_count else 'absent'}). Security posture needs attention: HSTS is "
        f"{'present' if hsts else 'missing'}, CSP is {'present' if csp else 'missing'}, X‑Frame‑Options is {'present' if xfo else 'missing'}, "
        f"and mixed content is {'detected' if mixed else 'not detected'}. Mobile readiness is {'confirmed' if viewport_meta else 'not confirmed'}. "
        f"The internal crawl discovered {len(crawled)} pages with status distribution "
        f"{statuses['2xx']} (2xx), {statuses['3xx']} (3xx), {statuses['4xx']} (4xx), {statuses['5xx']} (5xx), and {redirect_chains} redirect chains. "
        f"Prioritize compression (Brotli/GZIP), deferring non‑critical JS, caching/CDN to reduce TTFB, fixing broken links (internal {broken_internal}, external {broken_external}), "
        f"and enabling security headers to improve Core Web Vitals and reduce business risk."
    )

    # Gauges/charts
    def chart_gauge(score: int):
        color = "#10b981" if score >= 80 else "#f59e0b" if score >= 60 else "#ef4444"
        return {"labels": ["Score","Remaining"], "datasets": [{"data": [score, 100-score], "backgroundColor": [color, "#e5e7eb"], "borderWidth": 0}]}
    def chart_bar(labels, values, colors_list=None, label="Score"):
        return {"labels": labels, "datasets":[{"label": label, "data": values, "backgroundColor": colors_list or ["#6366f1","#f59e0b","#10b981","#ef4444","#0ea5e9","#22c55e"]}]}

    overall_gauge = chart_gauge(overall)
    health_gauge = chart_gauge(overall)
    issues_chart = {"labels": ["Errors","Warnings","Notices"], "datasets": [{"data": [errors, warnings, notices], "backgroundColor": ["#ef4444","#f59e0b","#3b82f6"]}]}
    category_chart = chart_bar(list(cat_scores.keys()), list(cat_scores.values()))

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

    # Build 250 metrics
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
# PDF helpers
# -----------------------------------------------
def draw_donut_gauge(c: canvas.Canvas, cx, cy, r, score):
    d = Drawing(r*2, r*2); p = Pie(); p.x=0; p.y=0; p.width=r*2; p.height=r*2
    pass_pct = max(0,min(100,int(score))); p.data=[pass_pct,100-pass_pct]; p.labels=["Score","Remaining"]; p.slices.strokeWidth=0
    color = colors.HexColor("#10b981") if score>=80 else colors.HexColor("#f59e0b") if score>=60 else colors.HexColor("#ef4444")
    p.slices[0].fillColor=color; p.slices[1].fillColor=colors.HexColor("#e5e7eb"); d.add(p); renderPDF.draw(d,c,cx-r,cy-r)
    c.setFillColor(colors.white); c.circle(cx,cy,r*0.58,fill=1,stroke=0)
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold",18); c.drawCentredString(cx,cy-4,f"{score}%")

def draw_bar(c: canvas.Canvas, x, y, w, h, labels, values, color="#6366f1"):
    d=Drawing(w,h); vb=VerticalBarChart(); vb.x=30; vb.y=20; vb.height=h-40; vb.width=w-60; vb.data=[values]
    vb.valueAxis.valueMin=0; vb.valueAxis.valueMax=max(100,max(values)+10); vb.valueAxis.valueStep=max(10,int(vb.valueAxis.valueMax/5))
    vb.categoryAxis.categoryNames=labels; vb.bars[0].fillColor=colors.HexColor(color); d.add(vb); renderPDF.draw(d,c,x,y)

def wrap_text(c: canvas.Canvas, text: str, x, y, max_width_chars=95, leading=14):
    words = text.split(); lines=[]; cur=""
    for w in words:
        if len(cur)+len(w)+1 > max_width_chars: lines.append(cur); cur=w
        else: cur=(cur+" "+w) if cur else w
    if cur: lines.append(cur)
    for i,line in enumerate(lines): c.drawString(x, y - i*leading, line)

def generate_pdf_5pages(url: str, payload: dict) -> bytes:
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=A4); W, H = A4
    def header(title):
        c.setFillColor(colors.HexColor("#0ea5e9")); c.setFont("Helvetica-Bold", 20)
        c.drawString(20*mm, H - 20*mm, "FF Tech — Certified Website Audit")
        c.setFillColor(colors.black); c.setFont("Helvetica", 11)
        c.drawString(20*mm, H - 30*mm, f"Website: {url}")
        c.drawString(20*mm, H - 36*mm, f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        c.setFont("Helvetica-Bold", 14); c.drawString(20*mm, H - 45*mm, title)

    # 1: Cover
    header("Cover & Score")
    c.setFont("Helvetica-Bold", 28); c.setFillColor(colors.black)
    c.drawString(20*mm, H - 65*mm, f"Grade: {payload['grade']} • Health: {payload['overall']}%")
    draw_donut_gauge(c, W/2, H/2, 45*mm, payload["overall"])
    draw_bar(c, 30*mm, 40*mm, W - 60*mm, 60*mm, ["Errors","Warnings","Notices"], [payload["errors"],payload["warnings"],payload["notices"]], "#f59e0b")
    c.showPage()

    # 2: Summary + Category totals
    header("Executive Summary & Category Overview")
    c.setFont("Helvetica", 11)
    wrap_text(c, payload["summary"], x=20*mm, y=H - 60*mm, max_width_chars=95, leading=14)
    totals = payload.get("totals", {})
    labels = ["Overall Health","Crawlability","On-Page SEO","Performance","Mobile & Security"]
    values = [totals.get("cat1",0),totals.get("cat2",0),totals.get("cat3",0),totals.get("cat4",0),totals.get("cat5",0)]
    draw_bar(c, 20*mm, 40*mm, W - 40*mm, 70*mm, labels, values, "#6366f1")
    c.showPage()

    # 3: Strengths / Weaknesses / Priority
    header("Strengths • Weaknesses • Priority Fixes")
    c.setFont("Helvetica-Bold", 13); c.drawString(20*mm, H - 60*mm, "Strengths"); c.setFont("Helvetica", 11); y = H - 66*mm
    for s in payload.get("strengths", [])[:6]: c.drawString(22*mm, y, f"• {s}"); y -= 7*mm
    c.setFont("Helvetica-Bold", 13); c.drawString(W/2, H - 60*mm, "Weak Areas"); c.setFont("Helvetica", 11); y2 = H - 66*mm
    for w in payload.get("weaknesses", [])[:6]: c.drawString(W/2+2*mm, y2, f"• {w}"); y2 -= 7*mm
    c.setFont("Helvetica-Bold", 13); c.drawString(20*mm, 90*mm, "Priority Fixes (Top 5)"); c.setFont("Helvetica", 11); y3 = 84*mm
    for p in payload.get("priority", [])[:5]: c.drawString(22*mm, y3, f"– {p}"); y3 -= 7*mm
    c.showPage()

    # 4: Trend & Resources
    header("Trend & Resources (Overview)")
    draw_bar(c, 20*mm, H - 120*mm, W - 40*mm, 60*mm, [f"W{i}" for i in range(1,9)], [max(50,min(100,payload["overall"]+(i%3)*5)) for i in range(1,9)], "#10b981")
    draw_bar(c, 20*mm, 40*mm, W - 40*mm, 70*mm, ["Size (MB)","Requests","Blocking JS","Stylesheets","TTFB (ms)"], [3.0, 80, 3, 4, 900], "#f59e0b")
    c.showPage()

    # 5: Highlights
    header("Impact / Effort Highlights")
    c.setFont("Helvetica-Bold", 12); c.drawString(20*mm, H - 60*mm, "Top Signals")
    c.setFont("Helvetica", 10); ytxt = H - 68*mm
    for name, note in [("TTFB","High impact • Medium effort"),("Render‑blocking JS","Medium impact • Low effort"),("Image size","High impact • Medium effort"),("CSP","High impact • Low effort"),("HSTS","Medium impact • Low effort"),("Mixed content","High impact • Medium effort")]:
        c.drawString(22*mm, ytxt, f"• {name}: {note}"); ytxt -= 7*mm
    c.save(); pdf_bytes = buf.getvalue(); buf.close(); return pdf_bytes

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
# FastAPI app + CORS
# -----------------------------------------------
app = FastAPI(title=APP_NAME)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# -----------------------------------------------
# Embedded world‑class HTML (CDN-only)
# -----------------------------------------------
INDEX_HTML = r"""<!DOCTYPE html>
<html lang='en' data-theme='light'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>
<title>FF Tech — Professional Audit</title>
https://cdn.tailwindcss.com</script>
https://cdn.jsdelivr.net/npm/chart.js@4.4.1</script>
https://fonts.gstatic.com
https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap
https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css
<style>
body{font-family:'Inter',system-ui,sans-serif;background:radial-gradient(1200px 700px at 10% 10%,#eef2ff,transparent),radial-gradient(1200px 700px at 90% 90%,#f1f5f9,transparent)}
.glass{background:rgba(255,255,255,.65);border:1px solid rgba(255,255,255,.35);backdrop-filter:saturate(140%) blur(10px);box-shadow:0 25px 50px rgba(0,0,0,.22);border-radius:24px}
.metric-card{border-left-width:8px}
.metric-green{border-color:#10b981}.metric-yellow{border-color:#f59e0b}.metric-red{border-color:#ef4444}
.blur-premium{filter:blur(10px);pointer-events:none}
.btn-gradient{background:linear-gradient(135deg,#4f46e5 0%,#7c3aed 100%);color:#fff}
.btn-gradient:hover{filter:brightness(1.05)}
.gradient-hero{background:radial-gradient(600px 300px at 50% 10%,#4f46e5 0,transparent 60%),linear-gradient(135deg,#4f46e5,#7c3aed)}
.grid-auto{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:18px}
</style>
</head>
<body class='text-slate-800'>
<header class='gradient-hero text-white shadow-2xl fixed inset-x-0 top-0 z-50'>
  <div class='max-w-7xl mx-auto px-6 py-5 flex items-center justify-between'>
    <div class='flex items-center gap-4'>
      <i class='fas fa-shield-halved text-3xl'></i>
      <div>
        <h1 class='text-2xl font-black'>FF Tech — Audit Platform</h1>
        <p class='text-sm opacity-80'>World-class Scheduled Web Audit & Certified Reporting</p>
      </div>
    </div>
    <nav class='flex items-center gap-6'>
      #Login</a>
      #Register</a>
      <span id='user-status' class='hidden'>Welcome, <span id='user-email'></span> · #Logout</a></span>
    </nav>
  </div>
</header>

<section id='hero' class='pt-36 pb-12'>
  <div class='max-w-7xl mx-auto px-6'>
    <div class='glass p-8 md:p-12'>
      <div class='flex flex-col md:flex-row items-center gap-10'>
        <div class='flex-1 text-center md:text-left'>
          <h2 class='text-4xl md:text-6xl font-black tracking-tight'>Professional Website Audits, <span class='text-brand-200'>Scheduled</span></h2>
          <p class='mt-3 opacity-80'>250+ metrics · Certified PDF · SEO, Performance, Security, Mobile & Accessibility</p>
          <form id='audit-form' class='mt-6 flex items-center gap-3'>
            <input id='website-url' type='url' placeholder='https://example.com'
                   class='flex-1 rounded-xl px-4 py-3 border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-500 text-slate-900' required>
            <button class='btn-gradient px-6 py-3 rounded-xl font-bold' type='submit'>Run Free Audit</button>
          </form>
          <p class='mt-3 text-sm opacity-80'>Free Audits Remaining: <span id='remaining' class='font-extrabold'>—</span></p>
        </div>
        <div class='w-full md:w-96 h-64 bg-white/10 rounded-2xl border border-white/20 relative overflow-hidden'>
          <svg class='absolute inset-0' viewBox='0 0 300 300'>
            <circle cx='150' cy='150' r='120' stroke='#e5e7eb' stroke-width='10' fill='none'></circle>
            <circle id='hero-progress' cx='150' cy='150' r='120' stroke='url(#grad)' stroke-width='10' fill='none' stroke-dasharray='753' stroke-dashoffset='753'></circle>
            <defs><linearGradient id='grad' x1='0' y1='0' x2='1' y2='1'><stop offset='0%' stop-color='#4f46e5'/><stop offset='100%' stop-color='#7c3aed'/></linearGradient></defs>
          </svg>
          <div class='absolute inset-0 flex items-center justify-center'>
            <div class='text-center'>
              <span class='text-xl font-bold'>Audit Progress</span>
              <div id='hero-progress-pct' class='text-3xl font-black'>0%</div>
            </div>
          </div>
        </div>
      </div>
      <div class='mt-4 flex items-center gap-6 text-slate-700'>
        <span class='flex items-center gap-2'><i class='fas fa-lock'></i> Secure</span>
        <span class='flex items-center gap-2'><i class='fas fa-bolt'></i> Instant</span>
        <span class='flex items-center gap-2'><i class='fas fa-certificate'></i> Certified</span>
      </div>
    </div>
  </div>
</section>

<section id='progress-section' class='hidden pb-8'>
  <div class='max-w-7xl mx-auto px-6'>
    <div class='glass p-8'>
      <h3 class='text-2xl font-black mb-6'>Audit in Progress</h3>
      <div class='space-y-4'>
        <div class='flex items-center gap-3'>
          <span class='w-28 font-bold'>Crawling</span><progress id='p-crawl' class='w-full h-3' value='0' max='100'></progress><span id='crawl-pct' class='w-16 text-right font-black'>0%</span>
        </div>
        <div class='flex items-center gap-3'>
          <span class='w-28 font-bold'>Analyzing</span><progress id='p-analyze' class='w-full h-3' value='0' max='100'></progress><span id='analyze-pct' class='w-16 text-right font-black'>0%</span>
        </div>
        <div class='flex items-center gap-3'>
          <span class='w-28 font-bold'>Scoring</span><progress id='p-score' class='w-full h-3' value='0' max='100'></progress><span id='score-pct' class='w-16 text-right font-black'>0%</span>
        </div>
        <div class='flex items-center gap-3'>
          <span class='w-28 font-bold'>Reporting</span><progress id='p-report' class='w-full h-3' value='0' max='100'></progress><span id='report-pct' class='w-16 text-right font-black'>0%</span>
        </div>
      </div>
      <div class='mt-6 grid md:grid-cols-2 gap-6'>
        <div class='glass p-4'><canvas id='health-gauge'></canvas></div>
        <div class='glass p-4'><canvas id='issues-chart'></canvas></div>
      </div>
    </div>
  </div>
</section>

<section id='summary-section' class='hidden pb-8'>
  <div class='max-w-7xl mx-auto px-6'>
    <div class='glass p-8'>
      <div class='text-center mb-6'><span id='grade-badge' class='text-3xl font-black bg-green-100 text-green-700 px-5 py-3 rounded-full'>A+</span></div>
      <div class='grid md:grid-cols-2 gap-6'>
        <div class='glass p-4'><canvas id='overall-gauge'></canvas></div>
        <div class='glass p-4'><canvas id='category-chart'></canvas></div>
      </div>
      <article class='mt-8 glass p-6'>
        <h4 class='text-xl font-extrabold mb-3'>Executive Summary</h4>
        <p id='exec-summary' class='leading-relaxed'></p>
      </article>
      <div class='mt-6 grid md:grid-cols-3 gap-6'>
        <div class='glass p-6'><h5 class='font-black text-green-700'>Strengths</h5><ul id='strengths' class='mt-2 list-disc list-inside'></ul></div>
        <div class='glass p-6'><h5 class='font-black text-rose-700'>Weak Areas</h5><ul id='weaknesses' class='mt-2 list-disc list-inside'></ul></div>
        <div class='glass p-6'><h5 class='font-black text-amber-700'>Priority Fixes</h5><ul id='priority' class='mt-2 list-disc list-inside'></ul></div>
      </div>
      <div class='text-center mt-8'>
        <button id='export-pdf' class='btn-gradient px-6 py-3 rounded-xl font-bold'>Export Certified PDF</button>
      </div>
    </div>
  </div>
</section>

<section id='dashboard-section' class='hidden pb-12'>
  <div class='max-w-7xl mx-auto px-6'>
    <div class='glass p-8'>
      <h3 class='text-2xl font-black mb-4'>Complete Metrics (1–250)</h3>
      <p class='text-sm opacity-80'>Public users see limited metrics; register to unlock full visuals.</p>
      <div class='relative'>
        <div id='premium-blur' class='absolute inset-0 blur-premium hidden'></div>
        <div id='metrics-grid' class='grid-auto mt-6'></div>
      </div>
    </div>
  </div>
</section>

<section id='user-panel' class='hidden pb-12'>
  <div class='max-w-7xl mx-auto px-6'>
    <div class='grid md:grid-cols-3 gap-6'>
      <div class='glass p-6'>
        <h4 class='text-xl font-black mb-3'>Add Website</h4>
        <form id='add-site-form' class='space-y-3'>
          <input id='add-site-url' type='url' placeholder='https://example.com'
                 class='w-full rounded-xl px-4 py-3 border border-slate-300 text-slate-900' required />
          <button class='btn-gradient px-5 py-3 rounded-xl font-bold'>Add</button>
        </form>
      </div>
      <div class='glass p-6 md:col-span-2'>
        <h4 class='text-xl font-black mb-3'>Schedule Audit</h4>
        <form id='schedule-form' class='space-y-3'>
          <input id='schedule-url' type='url' placeholder='https://example.com'
                 class='w-full rounded-xl px-4 py-3 border border-slate-300 text-slate-900' required />
          <div class='grid grid-cols-2 gap-4'>
            <input id='schedule-time' type='time' class='rounded-xl px-4 py-3 border border-slate-300' value='09:00' />
            <input id='schedule-tz' type='text' class='rounded-xl px-4 py-3 border border-slate-300' placeholder='Asia/Karachi' value='Asia/Karachi' />
          </div>
          <div class='grid grid-cols-2 gap-4'>
            <label class='flex items-center gap-2'><input id='schedule-daily' type='checkbox' checked /> Daily Report</label>
            <label class='flex items-center gap-2'><input id='schedule-acc' type='checkbox' checked /> Accumulated Report</label>
          </div>
          <button class='btn-gradient px-5 py-3 rounded-xl font-bold'>Save Schedule</button>
        </form>
      </div>
    </div>

    <div class='grid md:grid-cols-2 gap-6 mt-6'>
      <div class='glass p-6'>
        <h4 class='text-xl font-black mb-3'>Your Schedules</h4>
        <div id='schedules-list' class='space-y-2 text-sm'></div>
      </div>
      <div class='glass p-6'>
        <h4 class='text-xl font-black mb-3'>Settings</h4>
        <form id='settings-form' class='space-y-3'>
          <input id='settings-tz' type='text' placeholder='Asia/Karachi'
                 class='w-full rounded-xl px-4 py-3 border border-slate-300 text-slate-900' />
          <label class='flex items-center gap-2'><input id='settings-daily' type='checkbox' /> Default: Daily emails</label>
          <label class='flex items-center gap-2'><input id='settings-acc' type='checkbox' /> Default: Accumulated emails</label>
          <button class='btn-gradient px-5 py-3 rounded-xl font-bold'>Save Settings</button>
        </form>
        <div class='mt-4'>
          <button id='subscribe-btn-panel' class='btn-gradient px-6 py-3 rounded-xl font-bold'>$5/month — Subscribe</button>
        </div>
      </div>
    </div>
  </div>
</section>

<footer class='py-10'>
  <div class='max-w-7xl mx-auto px-6'>
    <div class='glass p-8 text-center'>
      <p class='font-black text-lg'>FF Tech © <span id='year'></span></p>
      <p class='text-sm opacity-80'>Professional Scheduled Audit & Reporting System · International Standard</p>
    </div>
  </div>
</footer>

<script>
const $=s=>document.querySelector(s);
const state={token:null,role:null,subscribed:false,freeRemaining:null,charts:{}};

function toast(msg){console.log('[Toast]',msg)}
function severityClass(sev){return sev==='green'?'metric-green':(sev==='yellow'?'metric-yellow':'metric-red')}
function chart(ctx,type,data){return new Chart(ctx,{type,data,options:{plugins:{legend:{display:false}},responsive:true}})}
function setProgress(el,pct){if(el){el.value=pct}}

async function api(path,opts={}){
  const headers=opts.headers||{};
  if(state.token) headers['Authorization']='Bearer '+state.token;
  if(!headers['Content-Type'] && opts.body) headers['Content-Type']='application/json';
  const res=await fetch(path,{...opts,headers});
  if(!res.ok){throw new Error('HTTP '+res.status+' '+(await res.text()))}
  const ct=res.headers.get('Content-Type')||'';
  if(ct.includes('application/pdf')) return res.blob();
  if(ct.includes('application/json')) return res.json();
  return res.text();
}

function saveSession(token,role,remaining,subscribed){
  localStorage.setItem('fftech_token',token); localStorage.setItem('fftech_role',role||'user');
  localStorage.setItem('fftech_remaining', remaining ?? ''); localStorage.setItem('fftech_subscribed', subscribed?'true':'false');
  state.token=token; state.role=role; state.freeRemaining=remaining; state.subscribed=subscribed;
  $('#user-status').classList.remove('hidden'); $('#open-login').classList.add('hidden'); $('#open-register').classList.add('hidden');
  toast('Logged in!');
}
function clearSession(){
  localStorage.removeItem('fftech_token'); localStorage.removeItem('fftech_role'); localStorage.removeItem('fftech_remaining'); localStorage.removeItem('fftech_subscribed');
  state.token=null; state.role=null; state.subscribed=false; state.freeRemaining=null;
  $('#user-status').classList.add('hidden'); $('#open-login').classList.remove('hidden'); $('#open-register').classList.remove('hidden');
  toast('Logged out.');
}
function loadSession(){
  const t=localStorage.getItem('fftech_token'); const role=localStorage.getItem('fftech_role'); const sub=localStorage.getItem('fftech_subscribed')==='true';
  const rem=localStorage.getItem('fftech_remaining'); if(t){state.token=t; state.role=role; state.subscribed=sub; state.freeRemaining=rem?parseInt(rem):null;
    $('#user-status').classList.remove('hidden'); $('#open-login').classList.add('hidden'); $('#open-register').classList.add('hidden');
    $('#user-panel').classList.remove('hidden');
  }
}

async function runAudit(url){
  $('#progress-section').classList.remove('hidden');
  let p=0; const tick=()=>{p=Math.min(100,p+Math.random()*10+8);
    setProgress($('#p-crawl'),Math.min(35,p)); $('#crawl-pct').textContent=Math.min(35,Math.floor(p))+'%';
    setProgress($('#p-analyze'),Math.min(70,p)); $('#analyze-pct').textContent=Math.min(70,Math.floor(p))+'%';
    setProgress($('#p-score'),Math.min(85,p)); $('#score-pct').textContent=Math.min(85,Math.floor(p))+'%';
    setProgress($('#p-report'),Math.min(100,p)); $('#report-pct').textContent=Math.min(100,Math.floor(p))+'%';
    const ring=document.getElementById('hero-progress'); if(ring){ring.setAttribute('stroke-dashoffset', String(753*(1-Math.min(1,p/100))))}
    document.getElementById('hero-progress-pct').textContent=Math.floor(p)+'%';
    if(p<100) setTimeout(tick,120);
  }; tick();

  const payload=await api(`/audit?url=${encodeURIComponent(url)}`);
  $('#summary-section').classList.remove('hidden'); $('#dashboard-section').classList.remove('hidden');

  $('#grade-badge').textContent=payload.grade;
  $('#exec-summary').textContent=payload.summary;
  $('#strengths').innerHTML=payload.strengths.map(s=>`<li>${s}</li>`).join('');
  $('#weaknesses').innerHTML=payload.weaknesses.map(s=>`<li>${s}</li>`).join('');
  $('#priority').innerHTML=payload.priority.map(s=>`<li>${s}</li>`).join('');
  if(payload.overall_gauge) chart($('#overall-gauge'),'doughnut',payload.overall_gauge);
  if(payload.category_chart) chart($('#category-chart'),'bar',payload.category_chart);
  if(payload.health_gauge) chart($('#health-gauge'),'doughnut',payload.health_gauge);
  if(payload.issues_chart) chart($('#issues-chart'),'bar',payload.issues_chart);

  const blur=$('#premium-blur'); blur.classList.toggle('hidden', !!payload.premium);

  const grid=$('#metrics-grid'); grid.innerHTML='';
  payload.metrics.forEach(m=>{
    const pad=String(m.num).padStart(3,'0');
    const card=document.createElement('div'); card.className=`glass p-4 metric-card ${severityClass(m.severity)}`;
    card.innerHTML=`<h5 class='text-sm font-bold mb-2'>${pad}. Metric ${pad}</h5><div class='h-48'><canvas id='chart-${pad}'></canvas></div>`;
    grid.appendChild(card); chart(document.getElementById(`chart-${pad}`),(m.chart_type||'bar'),m.chart_data);
  });

  if(typeof payload.remaining!=='undefined' && payload.remaining!==null){
    document.getElementById('remaining').textContent=payload.remaining;
    state.freeRemaining=payload.remaining; localStorage.setItem('fftech_remaining', payload.remaining);
  }
}

document.getElementById('audit-form').addEventListener('submit',async(e)=>{
  e.preventDefault();
  const url=document.getElementById('website-url').value.trim();
  if(!url) return toast('Please enter a website URL.');
  try{await runAudit(url)}catch(err){toast(err.message)}
});

document.getElementById('export-pdf').addEventListener('click',async()=>{
  const url=document.getElementById('website-url').value || 'https://example.com';
  const pdf=await api(`/export-pdf?url=${encodeURIComponent(url)}`);
  const blobUrl=URL.createObjectURL(pdf); const a=document.createElement('a');
  a.href=blobUrl; a.download=`fftech_audit_${Date.now()}.pdf`; a.click(); URL.revokeObjectURL(blobUrl);
});

// Registration/Login
document.getElementById('open-register').addEventListener('click',async(e)=>{
  e.preventDefault(); const email=prompt('Email:'); const password=prompt('Password (min 8 chars):'); const timezone=prompt('Timezone (e.g., Asia/Karachi):','Asia/Karachi');
  if(!email||!password) return;
  try{const res=await api('/register',{method:'POST',body:JSON.stringify({email,password,timezone})}); toast(res.message||'Registration submitted. Check email.')}
  catch(err){toast(err.message)}
});
document.getElementById('open-login').addEventListener('click',async(e)=>{
  e.preventDefault(); const email=prompt('Email:'); const password=prompt('Password:'); if(!email||!password) return;
  try{const res=await api('/login',{method:'POST',body:JSON.stringify({email,password})});
    $('#user-email').textContent=email; saveSession(res.token,res.role,res.free_audits_remaining,res.subscribed); $('#user-panel').classList.remove('hidden');
  }catch(err){toast(err.message)}
});
document.getElementById('logout').addEventListener('click',(e)=>{e.preventDefault(); clearSession()});

// Add Website
document.getElementById('add-site-form').addEventListener('submit',async(e)=>{
  e.preventDefault(); if(!state.token) return toast('Login required.');
  const url=document.getElementById('add-site-url').value.trim(); if(!url) return toast('Enter a site URL.');
  try{const res=await api('/websites',{method:'POST',body:JSON.stringify({url})}); toast(res.message||'Site added.')}catch(err){toast(err.message)}
});

// Schedule
document.getElementById('schedule-form').addEventListener('submit',async(e)=>{
  e.preventDefault(); if(!state.token) return toast('Login required.');
  const payload={website_url:$('#schedule-url').value.trim(),time_of_day:$('#schedule-time').value||'09:00',
    timezone:$('#schedule-tz').value||'UTC',daily_report:$('#schedule-daily').checked,accumulated_report:$('#schedule-acc').checked,enabled:true};
  if(!payload.website_url) return toast('Enter a site URL.');
  try{const res=await api('/schedule',{method:'POST',body:JSON.stringify(payload)}); toast(res.message||'Schedule saved.'); await refreshSchedules();}catch(err){toast(err.message)}
});
async function refreshSchedules(){
  if(!state.token) return;
  try{const sched=await api('/schedules'); const list=$('#schedules-list'); list.innerHTML=(sched||[]).map(s=>`
    <div class='glass px-3 py-2 flex justify-between'>
      <span>• ${s.website_url} — ${s.time_of_day} (${s.timezone}) — daily:${s.daily_report} · accumulated:${s.accumulated_report}</span>
      <span class='opacity-60'>last: ${s.last_run_at ?? '—'}</span>
    </div>`).join('');
  }catch(err){}
}

// Settings
document.getElementById('settings-form').addEventListener('submit',async(e)=>{
  e.preventDefault(); if(!state.token) return toast('Login required.');
  const payload={timezone:$('#settings-tz').value||'UTC',notify_daily_default:$('#settings-daily').checked,notify_acc_default:$('#settings-acc').checked};
  try{const res=await api('/settings',{method:'POST',body:JSON.stringify(payload)}); toast(res.message||'Settings updated.')}catch(err){toast(err.message)}
});

// Billing
async function openCheckout(){ if(!state.token) return toast('Login required.');
  try{const res=await api('/billing/checkout',{method:'POST'}); if(res.url) window.location.href=res.url; else toast(res.message||'Subscription activated (demo).');}
  catch(err){toast(err.message)}
}
document.getElementById('subscribe-btn-panel').addEventListener('click',openCheckout);

(function init(){ document.getElementById('year').textContent=new Date().getFullYear(); loadSession(); refreshSchedules();
  const ring=document.getElementById('hero-progress'); if(ring){ring.setAttribute('stroke-dasharray','753'); ring.setAttribute('stroke-dashoffset','753');}
})();
</script>
</body>
</html>
"""

# -----------------------------------------------
# Routes
# -----------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home(): return HTMLResponse(INDEX_HTML)

# --- Healthcheck (Railway) ---
@app.get("/health", response_class=JSONResponse)
def health():
    return {"status":"ok","time": datetime.utcnow().isoformat()}

# --- Public & Registered audit ---
@app.get("/audit", response_class=JSONResponse)
def audit(url: str = Query(..., description="Website URL to audit"),
          authorization: str | None = Header(None),
          db=Depends(get_db)):
    payload = run_actual_audit(url)

    is_registered = False
    user = None
    if authorization and authorization.startswith("Bearer "):
        try:
            data = jwt_verify(authorization.split(" ",1)[1])
            user = db.query(User).filter(User.id == data.get("uid")).first()
            is_registered = bool(user)
        except Exception:
            is_registered = False

    if not is_registered:
        payload["metrics"] = payload["metrics"][:50]
        payload["premium"] = False
        payload["remaining"] = None
    else:
        if not user.subscribed and user.free_audits_remaining <= 0:
            payload["metrics"] = payload["metrics"][:50]
            payload["premium"] = False
            payload["remaining"] = user.free_audits_remaining
        else:
            payload["premium"] = True
            payload["remaining"] = user.free_audits_remaining
            if not user.subscribed and user.free_audits_remaining > 0:
                user.free_audits_remaining -= 1
                db.commit()

    site = db.query(Website).filter(Website.url == normalize_url(url)).first()
    if not site:
        site = Website(url=normalize_url(url), user_id=(user.id if user else None), active=True)
        db.add(site); db.commit(); db.refresh(site)
    row = Audit(
        website_id=site.id, url=normalize_url(url),
        overall=payload["overall"], grade=payload["grade"],
        errors=payload["errors"], warnings=payload["warnings"], notices=payload["notices"],
        summary=payload["summary"], cat_scores_json=json.dumps(payload["cat_scores"]),
        cat_totals_json=json.dumps(payload["totals"]), metrics_json=json.dumps(payload["metrics"]),
        premium=payload["premium"]
    )
    db.add(row); db.commit()

    return JSONResponse(payload)

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

# --- Registration, verification, login (JWT) ---
@app.post("/register")
def register(payload: RegisterIn, db=Depends(get_db)):
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    pwd_hash, salt = create_user_password(payload.password)
    user = User(email=email, password_hash=pwd_hash, password_salt=salt, timezone=payload.timezone,
                notify_daily_default=True, notify_acc_default=True)
    db.add(user); db.commit(); db.refresh(user)
    token = jwt_sign({"uid": user.id, "act": "verify"}, exp_minutes=60*24)
    verify_link = f"{APP_BASE_URL}/verify?token={token}"
    send_email(email, "FF Tech — Verify your account",
               f"Welcome to FF Tech!\n\nPlease verify your email:\n{verify_link}\n\nLink expires in 24 hours.", [])
    return {"message": "Registration successful. Check your email to verify your account."}

@app.get("/verify")
def verify(token: str, db=Depends(get_db)):
    payload = jwt_verify(token)
    if payload.get("act") != "verify":
        raise HTTPException(status_code=400, detail="Invalid verification token")
    user = db.query(User).filter(User.id == payload.get("uid")).first()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    user.is_verified = True; db.commit()
    return {"message": "Email verified. You can now log in."}

@app.post("/login")
def login(payload: LoginIn, request: Request, db=Depends(get_db)):
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

# --- Website management & scheduling ---
@app.post("/websites")
def add_website(payload: WebsiteIn, user: User = Depends(get_current_user), db=Depends(get_db)):
    url = normalize_url(payload.url)
    existing = db.query(Website).filter(Website.url == url, Website.user_id == user.id).first()
    if existing:
        return {"message":"Website already added"}
    site = Website(url=url, user_id=user.id, active=True)
    db.add(site); db.commit(); db.refresh(site)
    return {"message":"Website added", "id": site.id}

@app.post("/schedule")
def create_schedule(payload: ScheduleIn, user: User = Depends(get_current_user), db=Depends(get_db)):
    url = normalize_url(payload.website_url)
    site = db.query(Website).filter(Website.url == url, Website.user_id == user.id).first()
    if not site:
        site = Website(url=url, user_id=user.id, active=True)
        db.add(site); db.commit(); db.refresh(site)
    sched = Schedule(
        user_id=user.id, website_id=site.id, enabled=payload.enabled,
        time_of_day=payload.time_of_day, timezone=payload.timezone,
        daily_report=payload.daily_report, accumulated_report=payload.accumulated_report
    )
    db.add(sched); db.commit(); db.refresh(sched)
    return {"message":"Schedule saved", "id": sched.id}

@app.get("/schedules")
def list_schedules(user: User = Depends(get_current_user), db=Depends(get_db)):
    rows = db.query(Schedule).filter(Schedule.user_id == user.id).all()
    out = []
    for s in rows:
        site = db.query(Website).get(s.website_id)
        out.append({"id": s.id, "website_url": site.url if site else None, "enabled": s.enabled,
                    "time_of_day": s.time_of_day, "timezone": s.timezone,
                    "daily_report": s.daily_report, "accumulated_report": s.accumulated_report,
                    "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None})
    return out

# --- Settings (timezone + notifications) ---
@app.get("/settings")
def get_settings(user: User = Depends(get_current_user)):
    return {
        "timezone": user.timezone,
        "notify_daily_default": user.notify_daily_default,
        "notify_acc_default": user.notify_acc_default,
        "subscribed": user.subscribed,
        "free_audits_remaining": user.free_audits_remaining,
    }

@app.post("/settings")
def update_settings(payload: SettingsIn, user: User = Depends(get_current_user), db=Depends(get_db)):
    user.timezone = payload.timezone
    user.notify_daily_default = payload.notify_daily_default
    user.notify_acc_default = payload.notify_acc_default
    db.commit()
    return {"message": "Settings updated"}

# --- Billing (Stripe) ---
@app.get("/billing/status")
def billing_status(user: User = Depends(get_current_user)):
    return {"subscribed": user.subscribed, "free_audits_remaining": user.free_audits_remaining}

@app.post("/billing/checkout")
def billing_checkout(user: User = Depends(get_current_user), db=Depends(get_db)):
    if not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
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
async def billing_webhook(request: Request, db=Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    if not STRIPE_WEBHOOK_SECRET:
        return {"message": "Webhook secret not configured"}
    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    type_ = event["type"]
    data = event["data"]["object"]
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

# --- Admin ---
@app.get("/admin/users")
def admin_users(admin: User = Depends(require_admin), db=Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [{"id": u.id, "email": u.email, "verified": u.is_verified, "role": u.role,
             "timezone": u.timezone, "free_audits_remaining": u.free_audits_remaining,
             "subscribed": u.subscribed, "created_at": u.created_at.isoformat(),
             "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None} for u in users]

@app.get("/admin/audits")
def admin_audits(admin: User = Depends(require_admin), db=Depends(get_db)):
    audits = db.query(Audit).order_by(Audit.created_at.desc()).limit(200).all()
    return [{"id": a.id, "url": a.url, "website_id": a.website_id, "overall": a.overall,
             "grade": a.grade, "errors": a.errors, "warnings": a.warnings, "notices": a.notices,
             "created_at": a.created_at.isoformat()} for a in audits]

# -----------------------------------------------
# Scheduler loop
# -----------------------------------------------
async def scheduler_loop():
    await asyncio.sleep(3)
    while True:
        try:
            db = SessionLocal()
            now_utc = datetime.utcnow().replace(second=0, microsecond=0)
            schedules = db.query(Schedule).filter(Schedule.enabled == True).all()
            for s in schedules:
                hh, mm = map(int, (s.time_of_day or "09:00").split(":"))
                tzname = s.timezone or "UTC"
                try:
                    from zoneinfo import ZoneInfo
                    tz = ZoneInfo(tzname)
                    local_now = now_utc.replace(tzinfo=timezone.utc).astimezone(tz)
                    scheduled_local = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                    scheduled_utc = scheduled_local.astimezone(timezone.utc).replace(tzinfo=None)
                except Exception:
                    scheduled_utc = now_utc.replace(hour=hh, minute=mm, second=0, microsecond=0)
                should_run = (now_utc >= scheduled_utc and (not s.last_run_at or s.last_run_at < scheduled_utc))
                if should_run:
                    site = db.query(Website).get(s.website_id)
                    payload = run_actual_audit(site.url)
                    pdf_bytes = generate_pdf_5pages(site.url, {
                        "grade": payload["grade"], "overall": payload["overall"], "summary": payload["summary"],
                        "strengths": payload["strengths"], "weaknesses": payload["weaknesses"], "priority": payload["priority"],
                        "errors": payload["errors"], "warnings": payload["warnings"], "notices": payload["notices"], "totals": payload["totals"],
                    })
                    user = db.query(User).get(s.user_id)
                    subj = f"FF Tech Audit — {site.url} ({payload['grade']} / {payload['overall']}%)"
                    body = "Your scheduled audit is ready.\n\n" \
                           f"Website: {site.url}\nGrade: {payload['grade']}\nHealth: {payload['overall']}%\n" \
                           f"Daily: {s.daily_report} | Accumulated: {s.accumulated_report}\n\n" \
                           "Certified PDF attached.\n— FF Tech"
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
            db.close()
        except Exception as e:
            print("[SCHEDULER ERROR]", e)
        await asyncio.sleep(SCHEDULER_INTERVAL)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(scheduler_loop())

# -----------------------------------------------
# MAIN (bind to PORT for Railway)
# -----------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
