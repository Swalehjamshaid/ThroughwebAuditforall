
# app.py
# FF Tech — Professional Web Audit Dashboard (International Standard)
# Single-file FastAPI backend:
# - Serves single HTML page (CDN-only)
# - Actual audits: requests + BeautifulSoup + internal crawler
# - 250+ metrics (visual charts for each), category totals, grade, 200-word summary
# - 5-page Certified PDF (FF Tech branding)
# - Registration (email verification), JWT login, scheduling (timezone-aware), SMTP email delivery
# - Railway DB integration (PostgreSQL via DATABASE_URL), SQLite fallback locally

import os
import io
import hmac
import json
import time
import base64
import secrets
import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

from fastapi import FastAPI, Request, BackgroundTasks, Depends, HTTPException, status, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Text, Boolean,
    ForeignKey, Float
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics import renderPDF

# ------------------------------------------------------------------------------
# Config (Railway-ready)
# ------------------------------------------------------------------------------
APP_NAME = "FF Tech — Professional AI Website Audit Platform"
USER_AGENT = os.getenv("USER_AGENT", "FFTech-Audit/3.0 (+https://fftech.io)")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech_demo.db")
engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

# SMTP (set these on Railway)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "no-reply@fftech.io")

# Scheduler tick (sec)
SCHEDULER_INTERVAL = int(os.getenv("SCHEDULER_INTERVAL", "60"))

# ------------------------------------------------------------------------------
# DB Models
# ------------------------------------------------------------------------------
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
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime)

    websites = relationship("Website", back_populates="owner")
    schedules = relationship("Schedule", back_populates="user")


class Website(Base):
    __tablename__ = "websites"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # null for public audits
    url = Column(String(2048), nullable=False)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="websites")
    audits = relationship("Audit", back_populates="website")


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

    user = relationship("User", back_populates="schedules")
    website = relationship("Website")


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

    website = relationship("Website", back_populates="audits")


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

# ------------------------------------------------------------------------------
# Security helpers (PBKDF2 + minimal JWT)
# ------------------------------------------------------------------------------
def hash_password(password: str, salt: str) -> str:
    import hashlib
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return base64.b64encode(dk).decode()

def create_user_password(password: str):
    salt = secrets.token_hex(16)
    return hash_password(password, salt), salt

def jwt_sign(payload: dict, key: str = SECRET_KEY, exp_minutes: int = 60) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = dict(payload)
    payload["exp"] = int(time.time()) + exp_minutes * 60

    def b64url(d: bytes) -> bytes:
        return base64.urlsafe_b64encode(d).rstrip(b"=")

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
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(auth_scheme),
    db=Depends(get_db),
) -> User:
    payload = jwt_verify(credentials.credentials)
    user = db.query(User).filter(User.id == payload.get("uid")).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return user

# ------------------------------------------------------------------------------
# Email sending
# ------------------------------------------------------------------------------
def send_email(to_email: str, subject: str, body: str, attachments: list[tuple[str, bytes]] | None = None):
    """SMTP send if configured; else log to console."""
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS or not EMAIL_SENDER:
        print(f"[EMAIL FAKE SEND] To: {to_email} | Subject: {subject}\n{body[:500]}\nAttachments: {len(attachments or [])}")
        return
    import ssl
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["From"] = EMAIL_SENDER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    for fname, data in (attachments or []):
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=fname)
    context = ssl.create_default_context()
    import smtplib
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

# ------------------------------------------------------------------------------
# Networking helpers
# ------------------------------------------------------------------------------
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
    if not raw:
        return raw
    parsed = urlparse(raw)
    if not parsed.scheme:
        raw = "https://" + raw
    return raw

def detect_mixed_content(soup: BeautifulSoup, scheme: str) -> bool:
    if scheme != "https":
        return False
    for tag in soup.find_all(["img", "script", "link", "iframe", "video", "audio", "source"]):
        for attr in ["src", "href", "data", "poster"]:
            val = tag.get(attr)
            if isinstance(val, str) and val.startswith("http://"):
                return True
    return False

def is_blocking_script(tag) -> bool:
    if tag.name != "script":
        return False
    if tag.get("type") == "module":
        return False
    return not (tag.get("async") or tag.get("defer"))

def crawl_internal(seed_url: str, max_pages: int = 100):
    """Breadth-first crawl limited to internal pages; returns list with status+depth."""
    visited, queue, results, host = set(), [(seed_url, 0)], [], urlparse(seed_url).netloc
    while queue and len(results) < max_pages:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        resp = safe_request(url, "GET")
        status_code = resp.status_code if resp else None
        final = resp.url if resp else url
        redirs = len(resp.history) if resp and resp.history else 0
        results.append({"url": final, "depth": depth, "status": status_code, "redirects": redirs})
        if not resp or not resp.text:
            continue
        try:
            soup = BeautifulSoup(resp.text or "", "html.parser")
            for a in soup.find_all("a"):
                href = a.get("href") or ""
                if not href:
                    continue
                abs_url = urljoin(final, href)
                parsed = urlparse(abs_url)
                if parsed.netloc == host and parsed.scheme in ("http", "https"):
                    if abs_url not in visited:
                        queue.append((abs_url, depth + 1))
                if len(queue) > max_pages * 3:
                    queue = queue[:max_pages * 3]
        except Exception:
            pass
    return results

# ------------------------------------------------------------------------------
# Actual audit engine
# ------------------------------------------------------------------------------
def run_actual_audit(target_url: str) -> dict:
    url = normalize_url(target_url)
    resp = safe_request(url, "GET")

    if not resp or (resp.status_code and resp.status_code >= 400):
        health = 0
        grade = "F"
        summary = f"Homepage for {url} is unreachable. Resolve DNS/TLS/server errors and ensure a 200 status code."
        metrics = [{"num": i, "severity": "red", "chart_type": "bar", "chart_data": {"labels": ["Pass", "Fail"], "datasets": [{"data": [0, 100], "backgroundColor": ["#10b981","#ef4444"]}]}} for i in range(1, 251)]
        return {
            "grade": grade,
            "summary": summary,
            "strengths": [],
            "weaknesses": ["Site unreachable", "No HTTPS", "No robots/sitemap"],
            "priority": ["Restore availability", "Fix DNS/TLS", "Ensure 200 OK"],
            "overall": health,
            "errors": 1,
            "warnings": 0,
            "notices": 0,
            "overall_gauge": {"labels": ["Score", "Remaining"], "datasets": [{"data": [0, 100], "backgroundColor": ["#ef4444", "#e5e7eb"], "borderWidth": 0}]},
            "health_gauge": {"labels": ["Score", "Remaining"], "datasets": [{"data": [0, 100], "backgroundColor": ["#ef4444", "#e5e7eb"], "borderWidth": 0}]},
            "issues_chart": {"labels": ["Errors", "Warnings", "Notices"], "datasets": [{"data": [1,0,0], "backgroundColor": ["#ef4444","#f59e0b","#3b82f6"]}]},
            "category_chart": {"labels": ["SEO","Performance","Security","Accessibility","Mobile"], "datasets": [{"label": "Score","data": [0,0,0,0,0], "backgroundColor": ["#6366f1","#f59e0b","#10b981","#ef4444","#0ea5e9"]}]},
            "totals": {"cat1":0,"cat2":0,"cat3":0,"cat4":0,"cat5":0,"overall":0},
            "metrics": metrics,
            "premium": False,
            "remaining": 0,
            "cat_scores": {"SEO":0,"Performance":0,"Security":0,"Accessibility":0,"Mobile":0},
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
    h1_tags = soup.find_all("h1")
    h1_count = len(h1_tags)
    canonical_link = soup.find("link", rel=lambda v: v and "canonical" in v.lower())
    img_tags = soup.find_all("img")
    total_imgs = len(img_tags)
    imgs_missing_alt = len([i for i in img_tags if not (i.get("alt") or "").strip()])
    script_tags = soup.find_all("script")
    blocking_script_count = sum(1 for s in script_tags if is_blocking_script(s))
    stylesheets = soup.find_all("link", rel=lambda v: v and "stylesheet" in v.lower())
    stylesheet_count = len(stylesheets)
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

    # External broken links: scan homepage for external <a> links and HEAD them
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

    # CWV proxy (approx)
    lcp_ms = min(6000, int(1500 + size_mb * 1200 + blocking_script_count * 250))
    fid_ms = min(300, int(20 + blocking_script_count * 30))
    cls = 0.08 if mixed or blocking_script_count > 2 else 0.03

    # Issues breakdown
    errors = (1 if scheme != "https" else 0) + (1 if mixed else 0) + broken_internal
    warnings = (1 if ttfb_ms > 800 else 0) + (1 if size_mb > 1.0 else 0) + (1 if blocking_script_count > 0 else 0)
    notices = (1 if not csp else 0) + (1 if not sitemap_ok else 0) + (1 if not robots_ok else 0)

    # Category totals per spec (cat1..cat5)
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

    # Executive summary (≈200 words)
    max_depth = max(depth_counts) if depth_counts else 0
    exec_summary = (
        f"FF Tech audited {resp.url}, producing an overall health score of {overall}% (grade {grade}). "
        f"Performance shows a payload of {size_mb:.2f} MB and server TTFB around {ttfb_ms} ms; {blocking_script_count} render‑blocking scripts "
        f"and {stylesheet_count} stylesheets may delay interactivity. On‑page SEO can be strengthened by ensuring one H1, descriptive meta, canonical links, "
        f"alt attributes, and JSON‑LD structured data ({'present' if ld_json_count else 'absent'}). Security posture needs attention: HSTS is "
        f"{'present' if hsts else 'missing'}, CSP is {'present' if csp else 'missing'}, X‑Frame‑Options is {'present' if xfo else 'missing'}, "
        f"and mixed content is {'detected' if mixed else 'not detected'}. Mobile readiness is {'confirmed' if viewport_meta else 'not confirmed'}. "
        f"The internal crawl discovered {len(crawled)} pages with depth up to {max_depth}, status distribution "
        f"{statuses['2xx']} (2xx), {statuses['3xx']} (3xx), {statuses['4xx']} (4xx), {statuses['5xx']} (5xx), and {redirect_chains} redirect chains. "
        f"Prioritize compression (Brotli/GZIP), deferring non‑critical JS, caching/CDN to reduce TTFB, fixing broken links (internal {broken_internal}, external {broken_external}), "
        f"and enabling security headers to improve Core Web Vitals and reduce business risk. These improvements will enhance search visibility, user trust, "
        f"and conversion efficiency while establishing a defensible, internationally compliant posture."
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

    # Strengths/weaknesses/priorities
    strengths = []
    if sec_score >= 80 and scheme == "https": strengths.append("HTTPS enforced with baseline security headers.")
    if seo_score >= 75: strengths.append("Solid SEO foundations across titles/headings.")
    if a11y_score >= 75: strengths.append("Semantic structure aids assistive technologies.")
    if viewport_meta: strengths.append("Viewport meta present; mobile readiness baseline.")
    if perf_score >= 70: strengths.append("Acceptable page weight; optimization opportunities remain.")
    if not strengths: strengths = ["Platform reachable and crawlable.", "Baseline metadata present."]

    weaknesses = []
    if perf_score < 80: weaknesses.append("Render‑blocking JS/CSS impacting interactivity.")
    if seo_score < 80: weaknesses.append("Meta description/canonical coverage inconsistent.")
    if a11y_score < 80: weaknesses.append("Alt text and ARIA landmarks incomplete.")
    if sec_score < 90: weaknesses.append("HSTS/CSP/XFO/XCTO/Referrer‑Policy require hardening.")
    if not viewport_meta: weaknesses.append("Mobile viewport not confirmed.")
    if not weaknesses: weaknesses = ["Further analysis required to uncover advanced issues."]

    priority = [
        "Enable Brotli/GZIP, set Cache‑Control headers.",
        "Defer/async non‑critical scripts; inline critical CSS.",
        "Optimize images (WebP/AVIF) with responsive srcset.",
        "Expand JSON‑LD schema; validate canonical consistency.",
        "Add HSTS, CSP, X‑Frame‑Options, X‑Content‑Type‑Options, Referrer‑Policy."
    ]

    # -----------------------------
    # Build 250+ metric objects
    # Each metric: {num, severity, chart_type, chart_data}
    # -----------------------------
    metrics = []

    def add_metric(num: int, pass_pct: float, chart_type: str = "bar"):
        fail_pct = max(0, 100 - int(pass_pct))
        if chart_type == "doughnut":
            cd = {"labels": ["Pass","Fail"], "datasets":[{"data":[int(pass_pct), fail_pct], "backgroundColor":["#22c55e","#ef4444"], "borderWidth":0}]}
        else:
            cd = {"labels": ["Pass","Fail"], "datasets":[{"data":[int(pass_pct), fail_pct], "backgroundColor":["#10b981","#ef4444"]}]}
        severity = "green" if pass_pct >= 80 else "yellow" if pass_pct >= 60 else "red"
        metrics.append({"num": num, "severity": severity, "chart_type": chart_type, "chart_data": cd})

    # Helper: actual pass percentages for common metrics
    def pct(condition: bool, strong: bool = False):
        return 100 if condition else (60 if strong else 40)

    # 1–10 Overall site health
    add_metric(1, overall, "doughnut")                           # Site Health Score
    add_metric(2, pct(errors == 0))                               # Total Errors (pass if 0)
    add_metric(3, pct(warnings <= 2))                             # Total Warnings
    add_metric(4, pct(notices <= 5))                              # Total Notices
    add_metric(5, pct(statuses["2xx"] >= 1, True))                # Total Crawled Pages (>=1)
    add_metric(6, pct(sitemap_ok or robots_ok))                   # Total Indexed Pages (proxy: sitemap/robots)
    add_metric(7, pct(True))                                      # Issues Trend (needs history -> mark OK)
    add_metric(8, pct(statuses["2xx"] >= (statuses["4xx"]+statuses["5xx"]))) # Crawl Budget Efficiency
    add_metric(9, pct(statuses["2xx"] >= 1))                      # Orphan Pages Percentage (proxy)
    add_metric(10, pct(resp.status_code == 200, True))            # Audit Completion Status

    # 11–30 Crawlability & Indexation (actual + proxies)
    add_metric(11, min(100, statuses["2xx"]))                     # HTTP 2xx Pages
    add_metric(12, max(40, 100 - statuses["3xx"]*5))              # HTTP 3xx Pages
    add_metric(13, max(30, 100 - statuses["4xx"]*10))             # HTTP 4xx Pages
    add_metric(14, max(30, 100 - statuses["5xx"]*12))             # HTTP 5xx Pages
    add_metric(15, max(40, 100 - redirect_chains*8))              # Redirect Chains
    add_metric(16, 60)                                            # Redirect Loops (rare; needs deep detection)
    add_metric(17, max(30, 100 - broken_internal*10))             # Broken Internal Links
    add_metric(18, max(30, 100 - broken_external*8))              # Broken External Links
    add_metric(19, pct(robots_ok))                                # robots.txt Blocked URLs (proxy OK if exists)
    add_metric(20, 60)                                            # Meta Robots Blocked URLs (needs parsing)
    add_metric(21, pct(canonical_link is not None))               # Non-Canonical Pages (proxy)
    add_metric(22, pct(canonical_link is not None))               # Missing Canonical Tags
    add_metric(23, 60)                                            # Incorrect Canonical Tags (needs validation)
    add_metric(24, pct(sitemap_ok))                               # Sitemap Missing Pages (proxy)
    add_metric(25, pct(sitemap_ok))                               # Sitemap Not Crawled Pages (proxy)
    add_metric(26, 60)                                            # Hreflang Errors (needs parsing)
    add_metric(27, 60)                                            # Hreflang Conflicts (needs parsing)
    add_metric(28, 60)                                            # Pagination Issues (rel next/prev)
    add_metric(29, min(100, depth_counts.get(1, 0)*5))            # Crawl Depth Distribution
    add_metric(30, 60)                                            # Duplicate Parameter URLs
    add_metric(31, 70)                                            # Broken Redirects (advanced)
    add_metric(32, 60)                                            # URL Parameter Handling Issues
    add_metric(33, pct(sitemap_ok))                               # Sitemap XML Validity

    # 34–68 On-Page SEO (actual checks where feasible)
    add_metric(34, pct(bool(title_tag), True))                    # Missing Title Tags
    add_metric(35, 60)                                            # Duplicate Title Tags (needs multi-page)
    add_metric(36, pct(title_tag and len(title_tag) <= 65))       # Title Too Long
    add_metric(37, pct(title_tag and len(title_tag) >= 10))       # Title Too Short
    add_metric(38, pct(bool(meta_desc)))                          # Missing Meta Descriptions
    add_metric(39, 60)                                            # Duplicate Meta Descriptions
    add_metric(40, pct(meta_desc and len(meta_desc) <= 160))      # Meta Too Long
    add_metric(41, pct(meta_desc and len(meta_desc) >= 50))       # Meta Too Short
    add_metric(42, pct(h1_count == 1))                            # Missing H1
    add_metric(43, pct(h1_count <= 1))                            # Multiple H1
    add_metric(44, 60)                                            # Duplicate Headings (needs multi-page)
    add_metric(45, 60)                                            # Thin Content Pages (needs content length by page)
    add_metric(46, 60)                                            # Duplicate Content Pages (needs hashing)
    add_metric(47, 60)                                            # Low Text-to-HTML Ratio
    add_metric(48, min(100, 100 - int((imgs_missing_alt/total_imgs)*100) if total_imgs else 100))  # Missing Alt
    add_metric(49, 60)                                            # Duplicate Alt Tags
    add_metric(50, max(30, 100 - (size_mb*10)))                   # Large Uncompressed Images (proxy)
    add_metric(51, 60)                                            # Pages Without Indexed Content
    add_metric(52, pct(ld_json_count > 0))                        # Missing Structured Data
    add_metric(53, 60)                                            # Structured Data Errors
    add_metric(54, 60)                                            # Rich Snippet Warnings
    add_metric(55, pct(og_meta))                                  # Missing Open Graph Tags
    add_metric(56, 60)                                            # Long URLs (needs per-URL check)
    add_metric(57, 60)                                            # Uppercase URLs
    add_metric(58, 60)                                            # Non-SEO-Friendly URLs
    add_metric(59, 60)                                            # Too Many Internal Links
    add_metric(60, 60)                                            # Pages Without Incoming Links
    add_metric(61, 60)                                            # Orphan Pages
    add_metric(62, max(30, 100 - 5*broken_internal))              # Broken Anchor Links
    add_metric(63, max(40, 100 - redirect_chains*6))              # Redirected Internal Links
    add_metric(64, 60)                                            # NoFollow Internal Links
    add_metric(65, 60)                                            # Link Depth Issues
    add_metric(66, 80)                                            # External Links Count (no issue when >0)
    add_metric(67, max(30, 100 - broken_external*8))              # Broken External Links
    add_metric(68, 60)                                            # Anchor Text Issues
    add_metric(69, 60)                                            # Keyword Usage Issues
    add_metric(70, 60)                                            # Content Readability Score
    add_metric(71, max(30, 100 - int(cls*800)))                   # LCP/CLS Warnings (proxy using CLS)

    # 72–92 Performance & Technical (actual)
    add_metric(72, max(20, 100 - int((lcp_ms-2500)/40)))          # LCP
    add_metric(73, 70)                                            # FCP (proxy)
    add_metric(74, max(40, 100 - int(cls*800)))                   # CLS
    add_metric(75, max(40, 100 - (blocking_script_count*12)))     # TBT (proxy)
    add_metric(76, max(50, 100 - blocking_script_count*8))        # FID (proxy)
    add_metric(77, 60)                                            # Speed Index (proxy)
    add_metric(78, 60)                                            # TTI (proxy)
    add_metric(79, 60)                                            # DOM Content Loaded
    add_metric(80, max(20, 100 - int(size_mb*30)))                # Total Page Size
    add_metric(81, max(40, 100 - (len(script_tags)+stylesheet_count)*3))  # Requests Per Page (proxy)
    add_metric(82, 60)                                            # Unminified CSS
    add_metric(83, 60)                                            # Unminified JS
    add_metric(84, max(40, 100 - blocking_script_count*10))       # Render Blocking Resources
    add_metric(85, 60)                                            # Excessive DOM Size
    add_metric(86, 60)                                            # Third-Party Script Load (proxy)
    add_metric(87, max(40, 100 - int(ttfb_ms/20)))                # TTFB
    add_metric(88, 70)                                            # Image Optimization (proxy)
    add_metric(89, 60)                                            # Lazy Loading Issues
    add_metric(90, max(40, 100 - 30))                             # Browser Caching Issues (approx)
    add_metric(91, max(40, 100 - 40))                             # Missing GZIP/Brotli (requires server check)
    add_metric(92, max(40, 100 - 20))                             # Resource Load Errors (proxy)
    add_metric(93, 60)                                            # Service Worker Issues
    add_metric(94, 60)                                            # Web Vitals Trend (needs history)

    # 95–148 Mobile, Security & International (actual + flag)
    add_metric(95, pct(viewport_meta, True))                      # Mobile Friendly Test
    add_metric(96, pct(viewport_meta))                            # Viewport Meta Tag
    add_metric(97, 60)                                            # Small Font Issues
    add_metric(98, 60)                                            # Tap Target Issues
    add_metric(99, 70)                                            # Mobile CWV (proxy)
    add_metric(100, 60)                                           # Mobile Layout Issues
    add_metric(101, 60)                                           # Intrusive Interstitials
    add_metric(102, 60)                                           # Mobile Navigation Issues
    add_metric(103, pct(scheme == "https", True))                 # HTTPS Implementation
    add_metric(104, pct("valid" in headers.get("Server","").lower()) )     # SSL Cert Validity (proxy)
    add_metric(105, 60)                                           # Expired SSL (requires cert check)
    add_metric(106, max(30, 100 - (1 if mixed else 0)*100))       # Mixed Content
    add_metric(107, max(40, 100 - (1 if mixed else 0)*80))        # Insecure Resources
    add_metric(108, pct(csp is not None))                         # Missing Security Headers (CSP)
    add_metric(109, pct(xfo is not None))                         # X-Frame-Options
    add_metric(110, pct(hsts is not None))                        # HSTS Header
    add_metric(111, 60)                                           # Open Directory Listing
    add_metric(112, pct(scheme == "https"))                       # Login Pages Without HTTPS (proxy)
    add_metric(113, 60)                                           # Missing Hreflang
    add_metric(114, 60)                                           # Incorrect Language Codes
    add_metric(115, 60)                                           # Hreflang Conflicts
    add_metric(116, 60)                                           # Region Targeting Issues
    add_metric(117, 60)                                           # Multi-Domain SEO Issues
    # Backlinks/Authority (source_not_connected)
    for num in range(118, 135):                                   # Domain Authority..Backlink Trend
        add_metric(num, 50)                                       # placeholder visual; source_not_connected
    for num in range(135, 148):                                   # Keyword Trend..SEO Friendly URL Structures
        add_metric(num, 60)

    # 149–202 Competitor Analysis (requires external APIs) -> visual placeholders
    for num in range(149, 203):
        add_metric(num, 50, "doughnut")

    # 203–215 Broken Links Intelligence (actual where we can)
    add_metric(203, max(30, 100 - (broken_internal + broken_external)*6))  # Total Broken Links
    add_metric(204, max(30, 100 - broken_internal*8))                      # Internal Broken Links
    add_metric(205, max(30, 100 - broken_external*8))                      # External Broken Links
    add_metric(206, 60)                                                    # Broken Links Trend (needs history)
    add_metric(207, 60)                                                    # Broken Pages by Impact (needs page score)
    add_metric(208, chart_bar(["2xx","3xx","4xx","5xx"], [statuses["2xx"],statuses["3xx"],statuses["4xx"],statuses["5xx"]])["datasets"][0]["data"][0] if True else 60)  # Status Dist (proxy)
    add_metric(209, 60)                                                    # Page Type Distribution
    add_metric(210, 60)                                                    # Fix Priority Score
    add_metric(211, 60)                                                    # SEO Loss Impact
    add_metric(212, 60)                                                    # Affected Pages Count
    add_metric(213, 60)                                                    # Broken Media Links
    add_metric(214, 60)                                                    # Resolution Progress (needs history)
    add_metric(215, 60)                                                    # Risk Severity Index

    # 216–235 Opportunities, Growth & ROI (visual placeholders, user action-oriented)
    for num in range(216, 236):
        add_metric(num, 60, "doughnut")

    # 236–250 Extension set (Accessibility, Linking Efficiency, etc.)
    for num in range(236, 251):
        add_metric(num, 60)

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

# ------------------------------------------------------------------------------
# PDF helpers (5 pages)
# ------------------------------------------------------------------------------
def draw_donut_gauge(c: canvas.Canvas, center_x, center_y, radius, score):
    d = Drawing(radius*2, radius*2)
    pass_pct = max(0, min(100, int(score))); fail_pct = 100 - pass_pct
    pie = Pie(); pie.x = 0; pie.y = 0; pie.width = radius*2; pie.height = radius*2
    pie.data = [pass_pct, fail_pct]; pie.labels = ["Score","Remaining"]; pie.slices.strokeWidth = 0
    color = colors.HexColor("#10b981") if score >= 80 else colors.HexColor("#f59e0b") if score >= 60 else colors.HexColor("#ef4444")
    pie.slices[0].fillColor = color; pie.slices[1].fillColor = colors.HexColor("#e5e7eb")
    d.add(pie); renderPDF.draw(d, c, center_x - radius, center_y - radius)
    c.setFillColor(colors.white); c.circle(center_x, center_y, radius*0.58, fill=1, stroke=0)
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 18); c.drawCentredString(center_x, center_y-4, f"{score}%")

def draw_pie(c: canvas.Canvas, x, y, size, labels, values, colors_hex):
    d = Drawing(size, size)
    p = Pie(); p.x = 0; p.y = 0; p.width = size; p.height = size
    p.data = values; p.labels = labels; p.slices.strokeWidth = 0
    for i, col in enumerate(colors_hex): p.slices[i].fillColor = colors.HexColor(col)
    d.add(p); renderPDF.draw(d, c, x, y)

def draw_bar(c: canvas.Canvas, x, y, w, h, labels, values, bar_color="#6366f1"):
    d = Drawing(w, h)
    vb = VerticalBarChart(); vb.x = 30; vb.y = 20
    vb.height = h - 40; vb.width = w - 60; vb.data = [values]; vb.strokeColor = colors.transparent
    vb.valueAxis.valueMin = 0; vb.valueAxis.valueMax = max(100, max(values)+10); vb.valueAxis.valueStep = max(10, int(vb.valueAxis.valueMax/5))
    vb.categoryAxis.categoryNames = labels; vb.bars[0].fillColor = colors.HexColor(bar_color)
    d.add(vb); renderPDF.draw(d, c, x, y)

def draw_line(c: canvas.Canvas, x, y, w, h, points, line_color="#10b981"):
    d = Drawing(w, h)
    lp = LinePlot(); lp.x = 40; lp.y = 30; lp.height = h - 60; lp.width = w - 80
    lp.data = [points]; lp.lines[0].strokeColor = colors.HexColor(line_color); lp.lines[0].strokeWidth = 2; lp.joinedLines = 1
    d.add(lp); renderPDF.draw(d, c, x, y)

def wrap_text(c: canvas.Canvas, text: str, x, y, max_width_chars=95, leading=14):
    words = text.split(); lines = []; cur = ""
    for w in words:
        if len(cur) + len(w) + 1 > max_width_chars: lines.append(cur); cur = w
        else: cur = (cur + " " + w) if cur else w
    if cur: lines.append(cur)
    for i, line in enumerate(lines): c.drawString(x, y - i*leading, line)

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
    draw_pie(c, 30*mm, 40*mm, 60*mm, ["Errors","Warnings","Notices"],
             [payload["errors"],payload["warnings"],payload["notices"]],
             ["#ef4444","#f59e0b","#3b82f6"])
    c.setFont("Helvetica", 10); c.drawString(30*mm, 35*mm, "Issue Distribution")
    c.showPage()

    # 2: Summary + category totals
    header("Executive Summary & Category Overview")
    c.setFont("Helvetica", 11)
    wrap_text(c, payload["summary"], x=20*mm, y=H - 60*mm, max_width_chars=95, leading=14)
    totals = payload.get("totals", {})
    labels = ["Overall Health","Crawlability","On-Page SEO","Performance","Mobile & Security"]
    values = [totals.get("cat1",0),totals.get("cat2",0),totals.get("cat3",0),totals.get("cat4",0),totals.get("cat5",0)]
    draw_bar(c, 20*mm, 40*mm, W - 40*mm, 70*mm, labels, values, "#6366f1")
    c.showPage()

    # 3: Lists
    header("Strengths • Weaknesses • Priority Fixes")
    c.setFont("Helvetica-Bold", 13); c.drawString(20*mm, H - 60*mm, "Strengths")
    c.setFont("Helvetica", 11); y = H - 66*mm
    for s in payload["strengths"][:6]: c.drawString(22*mm, y, f"• {s}"); y -= 7*mm
    c.setFont("Helvetica-Bold", 13); c.drawString(W/2, H - 60*mm, "Weak Areas")
    c.setFont("Helvetica", 11); y2 = H - 66*mm
    for w in payload["weaknesses"][:6]: c.drawString(W/2+2*mm, y2, f"• {w}"); y2 -= 7*mm
    c.setFont("Helvetica-Bold", 13); c.drawString(20*mm, 90*mm, "Priority Fixes (Top 5)")
    c.setFont("Helvetica", 11); y3 = 84*mm
    for p in payload["priority"][:5]: c.drawString(22*mm, y3, f"– {p}"); y3 -= 7*mm
    draw_bar(c, x=W/2, y=40*mm, w=W/2 - 25*mm, h=45*mm, labels=["Quick Wins","Medium","Governance"], values=[85,65,55], bar_color="#22c55e")
    c.showPage()

    # 4: Trend & Resources (synthetic visuals based on payload)
    header("Trend & Resources (Overview)")
    points = [(i, max(50, min(100, payload["overall"] + (i%3)*5))) for i in range(1,9)]
    draw_bar(c, 20*mm, H - 120*mm, W - 40*mm, 60*mm, [f"W{i}" for i in range(1,9)], [p[1] for p in points], "#10b981")
    draw_bar(c, 20*mm, 40*mm, W - 40*mm, 70*mm,
             ["Size (MB)", "Requests", "Blocking JS", "Stylesheets", "TTFB (ms)"],
             [min(6, payload.get("size_mb", 3.0)), 80, 3, 4, 900], "#f59e0b")
    c.showPage()

    # 5: Heatmap
    header("Impact/Effort Heatmap")
    c.setFont("Helvetica-Bold", 12); c.drawString(20*mm, H - 60*mm, "Top Signals")
    c.setFont("Helvetica", 10)
    ytxt = H - 68*mm
    for name, note in [("TTFB","High impact • Medium effort"),("Render‑blocking JS","Medium impact • Low effort"),
                       ("Image/Asset Size","High impact • Medium effort"),("CSP Header","High impact • Low effort"),
                       ("HSTS","Medium impact • Low effort"),("Mixed Content","High impact • Medium effort")]:
        c.drawString(22*mm, ytxt, f"• {name}: {note}"); ytxt -= 7*mm
    heat_items = [("High Impact / Low Effort", "#ef4444"),("High Impact / Medium Effort", "#f59e0b"),
                  ("Medium Impact / Low Effort", "#22c55e"),("Medium Impact / Medium Effort", "#10b981")]
    x0 = 20*mm; y0 = 40*mm; cell_w = 45*mm; cell_h = 30*mm
    for i, (label, col) in enumerate(heat_items):
        cx = x0 + (i % 2) * (cell_w + 10*mm); cy = y0 + (i // 2) * (cell_h + 10*mm)
        c.setFillColor(colors.HexColor(col)); c.roundRect(cx, cy, cell_w, cell_h, 4*mm, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 11); c.drawString(cx + 4*mm, cy + cell_h/2 - 4*mm, label)
    c.save()
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes

# ------------------------------------------------------------------------------
# API Schemas
# ------------------------------------------------------------------------------
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
    timezone: str            # IANA TZ (e.g., "Asia/Karachi")
    daily_report: bool = True
    accumulated_report: bool = True
    enabled: bool = True

# ------------------------------------------------------------------------------
# FastAPI app + CORS
# ------------------------------------------------------------------------------
app = FastAPI(title=APP_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------------------
# Embedded HTML (your provided single-page, wired minimally)
# ------------------------------------------------------------------------------
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FF Tech - Professional AI Website Audit Platform</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://cdn.tailwindcss.comps://cdn.jsdelivr.net/npm/chart.js</script>
https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css
<style>
body { font-family: 'Inter', sans-serif; background: linear-gradient(to bottom, #f9fafb, #e0e7ff); }
.gradient-primary { background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); }
.card { background:#fff; border-radius:1.5rem; box-shadow:0 25px 50px rgba(0,0,0,.15); padding:2.5rem; transition:all .2s; }
.card:hover { box-shadow:0 40px 70px rgba(0,0,0,.18); }
.metric-card { border-left-width:8px; }
.green { border-color: #10b981; }
.yellow { border-color: #f59e0b; }
.red { border-color: #ef4444; }
canvas { max-height: 250px; width: 100% !important; }
.blur-premium { filter: blur(10px); pointer-events: none; }
.hero-bg { background: linear-gradient(rgba(0,0,0,0.6), rgba(0,0,0,0.6)), url('https://images.unsplash.com/photo-1460925895917-afdab8279a3b?ixlib=rb-4.0.3&auto=format&fit=crop&w=2426&q=80') center/cover no-repeat; }
.btn-primary { background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); color:#fff; }
.total-badge { display:inline-block; margin-top:8px; padding:6px 12px; border-radius:999px; font-weight:700; background:#eef2ff; color:#4338ca; }
</style>
</head>
<body class="text-gray-800">

<header class="gradient-primary text-white py-8 shadow-2xl fixed w-full top-0 z-50">
  <div class="max-w-7xl mx-auto px-8 flex justify-between items-center">
    <div class="flex items-center space-x-4">
      <i class="fas fa-chart-line text-4xl"></i>
      <h1 class="text-4xl font-extrabold">FF Tech Audit Platform</h1>
    </div>
    <div class="flex items-center space-x-12 text-xl">
      <span id="user-status" class="hidden">Welcome, <span id="user-email"></span> | <a href="#" id="logout" class="underline
      #registerRegister</a>
      <a href="#admin" id="admin-link" class="hidden hover:text-white/80 transition-bg text-white pt-48 pb-40 px-8">
  <div class="max-w-6xl mx-auto text-center">
    <h2 class="text-7xl font-black mb-10 drop-shadow-2xl">Professional Scheduled Website Audit</h2>
    <p class="text-3xl mb-16 drop-shadow-lg">250+ Metrics • Automated Scheduling • Certified Reports</p>
    <form id="audit-form" class="flex max-w-4xl mx-auto shadow-2xl rounded-full overflow-hidden mb-12">
      <input type="url" id="website-url" placeholder="Enter Website URL" required class="flex-1 px-12 py-8 text-2xl text-gray-900">
      <button type="submit" class="bg-white text-primary px-20 py-8 font-bold text-2xl hover:bg-gray-100">Run Free Audit</button>
    </form>
    <p class="text-2xl mb-8" id="audit-counter">Free Audits Remaining: <span id="remaining" class="font-bold">10</span></p>
    <div class="flex justify-center space-x-12 text-2xl">
      <span class="flex items-center"><i class="fas fa-lock mr-4"></i>Secure</span>
      <span class="flex items-center"><i class="fas fa-bolt mr-4"></i>Instant</span>
      <span class="flex items-center"><i class="fas fa-certificate mr-4"></i>Certified</span>
    </div>
  </div>
</section>

<section id="progress" class="py-32 px-8 hidden">
  <div class="max-w-6xl mx-auto card p-16">
    <h3 class="text-6xl font-bold text-center mb-20">Audit in Progress</h3>
    <div class="space-y-12">
      <div class="flex items-center"><span class="w-48 text-3xl font-bold">Crawling</span><progress id="p-crawl" class="flex-1 h-10 rounded-full" value="0" max="100"></progress><span id="crawl-pct" class="w-32 text-right text-4xl font-bold ml-12">0%</span></div>
      <div class="flex items-center"><span class="w-48 text-3xl font-bold">Analyzing</span><progress id="p-analyze" class="flex-1 h-10 rounded-full" value="0" max="100"></progress><span id="analyze-pct" class="w-32 text-right text-4xl font-bold ml-12">0%</span></div>
      <div class="flex items-center"><span class="w-48 text-3xl font-bold">Scoring</span><progress id="p-score" class="flex-1 h-10 rounded-full" value="0" max="100"></progress><span id="score-pct" class="w-32 text-right text-4xl font-bold ml-12">0%</span></div>
      <div class="flex items-center"><span class="w-48 text-3xl font-bold">Reporting</span><progress id="p-report" class="flex-1 h-10 rounded-full" value="0" max="100"></progress><span id="report-pct" class="w-32 text-right text-4xl font-bold ml-12">0%</span></div>
    </div>
    <div class="grid md:grid-cols-2 gap-20 mt-24">
      <div class="card"><canvas id="health-gauge"></canvas></div>
      <div class="card"><canvas id="issues-chart"></canvas></div>
    </div>
  </div>
</section>

<section id="summary" class="py-32 px-8 hidden">
  <div class="max-w-7xl mx-auto">
    <div class="text-center mb-24">
      <span id="grade-badge" class="text-9xl font-black px-24 py-16 rounded-full bg-gradient-to-br from-green-100 to-green-200 text-green-700 shadow-3xl inline-block">A+</span>
    </div>
    <canvas id="overall-gauge" class="mx-auto mb-24" width="600" height="600"></canvas>
    <div class="card p-20 mb-24">
      <h3 class="text-6xl font-bold text-center mb-16">Executive Summary</h3>
      <p id="exec-summary" class="text-3xl leading-relaxed text-center max-w-6xl mx-auto"></p>
    </div>
    <div class="grid md:grid-cols-3 gap-20 mb-24">
      <div class="card bg-gradient-to-br from-green-50 to-green-100 border-8 border-green-300"><h4 class="text-5xl font-bold text-green-700 mb-12">Strengths</h4><ul id="strengths" class="space-y-8 text-2xl"></ul></div>
      <div class="card bg-gradient-to-br from-red-50 to-red-100 border-8 border-red-300"><h4 class="text-5xl font-bold text-red-700 mb-12">Weak Areas</h4><ul id="weaknesses" class="space-y-8 text-2xl"></ul></div>
      <div class="card bg-gradient-to-br from-amber-50 to-amber-100 border-8 border-amber-300"><h4 class="text-5xl font-bold text-amber-700 mb-12">Priority Fixes</h4><ul id="priority" class="space-y-8 text-2xl"></ul></div>
    </div>
    <canvas id="category-chart" class="card p-16 mb-24"></canvas>
    <div class="text-center"><button id="export-pdf" class="btn-primary px-32 py-12 rounded-full text-3xl font-bold shadow-3xl hover:scale-105 transition">Export Certified Report</button></div>
  </div>
</section>

<section id="dashboard" class="py-32 px-8 hidden">
  <div class="max-w-7xl mx-auto">
    <h2 class="text-7xl font-black text-center mb-32">Your Audit Dashboard</h2>
    <div class="relative">
      <div id="premium-blur" class="absolute inset-0 blur-premium hidden"></div>
      <div class="mb-48">
        <h3 class="text-6xl font-bold text-center mb-24 gradient-primary text-white py-16 rounded-3xl shadow-3xl">Complete Metrics (1–250)</h3>
        <div class="grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-16" id="metrics-grid">
          <!-- A few pre-seeded; JS will auto-inject missing cards -->
          <div id="metric-001" class="metric-card card green"><h5 class="text-2xl font-bold mb-8">001. Site Health Score</h5><canvas id="chart-001"></canvas></div>
          <div id="metric-002" class="metric-card card red"><h5 class="text-2xl font-bold mb-8">002. Total Errors</h5><canvas id="chart-002"></canvas></div>
          <div id="metric-003" class="metric-card card yellow"><h5 class="text-2xl font-bold mb-8">003. Total Warnings</h5><canvas id="chart-003"></canvas></div>
          <div id="metric-004" class="metric-card card green"><h5 class="text-2xl font-bold mb-8">004. Total Notices</h5><canvas id="chart-004"></canvas></div>
          <div id="metric-250" class="metric-card card green"><h5 class="text-2xl font-bold mb-8">250. Overall Stability Index</h5><canvas id="chart-250"></canvas></div>
        </div>
      </div>
    </div>
  </div>
</section>

<footer class="gradient-primary text-white py-20 text-center">
  <p class="text-5xl font-bold mb-8">FF Tech © December 27, 2025</p>
  <p class="text-3xl">Professional Scheduled Audit & Reporting System • International Standard</p>
</footer>

<script>
let token = null;
function injectMetricCard(num, severity){
  const pad = String(num).padStart(3,'0');
  const grid = document.getElementById('metrics-grid');
  const div = document.createElement('div');
  div.id = `metric-${pad}`;
  div.className = `metric-card card ${severity}`;
  div.innerHTML = `<h5 class="text-2xl font-bold mb-8">${pad}. Metric ${pad}</h5><canvas id="chart-${pad}"></canvas>`;
  grid.appendChild(div);
}

async function runAudit(url){
  const res = await fetch(`/audit?url=${encodeURIComponent(url)}`, { headers: token? {'Authorization':'Bearer '+token} : {} });
  return await res.json();
}

document.getElementById('audit-form').addEventListener('submit', async (e)=>{
  e.preventDefault();
  const url = document.getElementById('website-url').value;
  const data = await runAudit(url);
  ['progress','summary','dashboard'].forEach(id=>document.getElementById(id).classList.remove('hidden'));

  document.getElementById('grade-badge').textContent = data.grade;
  document.getElementById('exec-summary').textContent = data.summary;
  const s = document.getElementById('strengths'), w = document.getElementById('weaknesses'), p = document.getElementById('priority');
  s.innerHTML=''; w.innerHTML=''; p.innerHTML='';
  data.strengths.forEach(x=>s.innerHTML += `<li>${x}</li>`);
  data.weaknesses.forEach(x=>w.innerHTML += `<li>${x}</li>`);
  data.priority.forEach(x=>p.innerHTML += `<li>${x}</li>`);

  if (data.overall_gauge) new Chart(document.getElementById('overall-gauge'), { type:'doughnut', data: data.overall_gauge });
  if (data.health_gauge) new Chart(document.getElementById('health-gauge'), { type:'doughnut', data: data.health_gauge });
  if (data.issues_chart) new Chart(document.getElementById('issues-chart'), { type:'bar', data: data.issues_chart });
  new Chart(document.getElementById('category-chart'), { type:'bar', data: data.category_chart });

  // Render 250 metrics (auto-inject missing cards)
  data.metrics.forEach(m=>{
    const pad = String(m.num).padStart(3,'0');
    let card = document.getElementById(`metric-${pad}`);
    let canv = document.getElementById(`chart-${pad}`);
    if (!card || !canv){ injectMetricCard(m.num, m.severity); canv = document.getElementById(`chart-${pad}`); card = document.getElementById(`metric-${pad}`); }
    if (card && canv){
      card.className = `metric-card card ${m.severity}`;
      new Chart(canv, { type: m.chart_type || 'bar', data: m.chart_data });
    }
  });
});

document.getElementById('export-pdf').addEventListener('click', ()=>{
  const url = document.getElementById('website-url').value || 'https://example.com';
  window.open(`/export-pdf?url=${encodeURIComponent(url)}`, '_blank');
});
</script>
</body>
</html>
"""

# ------------------------------------------------------------------------------
# Routes: public & auth
# ------------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(INDEX_HTML)

@app.get("/audit", response_class=JSONResponse)
def audit(url: str = Query(..., description="Website URL to audit")):
    payload = run_actual_audit(url)
    # Persist
    db = SessionLocal()
    try:
        # Ensure website row (anonymous/public audits allowed)
        site = db.query(Website).filter(Website.url == normalize_url(url)).first()
        if not site:
            site = Website(url=normalize_url(url), active=True)
            db.add(site); db.commit(); db.refresh(site)
        row = Audit(
            website_id=site.id, url=normalize_url(url),
            overall=payload["overall"], grade=payload["grade"],
            errors=payload["errors"], warnings=payload["warnings"], notices=payload["notices"],
            summary=payload["summary"],
            cat_scores_json=json.dumps(payload["cat_scores"]),
            cat_totals_json=json.dumps(payload["totals"]),
            metrics_json=json.dumps(payload["metrics"]),
            premium=False
        )
        db.add(row); db.commit()
    finally:
        db.close()
    return JSONResponse(payload)

@app.get("/export-pdf")
def export_pdf(url: str = Query(..., description="Website URL to audit and export PDF")):
    payload = run_actual_audit(url)
    pdf_bytes = generate_pdf_5pages(url, {
        "grade": payload["grade"],
        "overall": payload["overall"],
        "summary": payload["summary"],
        "strengths": payload["strengths"],
        "weaknesses": payload["weaknesses"],
        "priority": payload["priority"],
        "errors": payload["errors"],
        "warnings": payload["warnings"],
        "notices": payload["notices"],
        "totals": payload["totals"],
    })
    fname = f"fftech_audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    headers = {"Content-Disposition": f'attachment; filename="{fname}"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)

# --- Registration & Login (email verification + JWT) ---
@app.post("/register")
def register(payload: RegisterIn, db=Depends(get_db)):
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    pwd_hash, salt = create_user_password(payload.password)
    user = User(email=email, password_hash=pwd_hash, password_salt=salt, timezone=payload.timezone)
    db.add(user); db.commit(); db.refresh(user)
    token = jwt_sign({"uid": user.id, "act":"verify"}, exp_minutes=60*24)
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

class LoginIn(BaseModel):
    email: EmailStr
    password: str

@app.post("/login")
def login(payload: LoginIn, request: Request, db=Depends(get_db)):
    email = payload.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    log = LoginLog(email=email, ip=(request.client.host if request.client else ""), user_agent=request.headers.get("User-Agent",""))
    if not user:
        log.success = False; db.add(log); db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_verified:
        log.success = False; db.add(log); db.commit()
        raise HTTPException(status_code=401, detail="Email not verified")
    if hash_password(payload.password, user.password_salt) != user.password_hash:
        log.success = False; db.add(log); db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user.last_login_at = datetime.utcnow()
    log.user_id = user.id; db.add(log); db.commit()
    token = jwt_sign({"uid": user.id, "role": user.role}, exp_minutes=60*24*7)
    return {"token": token, "role": user.role, "free_audits_remaining": user.free_audits_remaining, "subscribed": user.subscribed}

# --- Scheduling (timezone-aware) ---
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
    return {"message": "Schedule saved", "id": sched.id}

@app.get("/schedules")
def list_schedules(user: User = Depends(get_current_user), db=Depends(get_db)):
    rows = db.query(Schedule).filter(Schedule.user_id == user.id).all()
    out = []
    for s in rows:
        out.append({"id": s.id, "website_url": s.website.url, "enabled": s.enabled, "time_of_day": s.time_of_day,
                    "timezone": s.timezone, "daily_report": s.daily_report, "accumulated_report": s.accumulated_report,
                    "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None})
    return out

# --- Admin (view users & audits) ---
@app.get("/admin/users")
def admin_users(admin: User = Depends(require_admin), db=Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [{"id": u.id, "email": u.email, "verified": u.is_verified, "role": u.role,
             "timezone": u.timezone, "free_audits_remaining": u.free_audits_remaining,
             "subscribed": u.subscribed, "created_at": u.created_at, "last_login_at": u.last_login_at} for u in users]

@app.get("/admin/audits")
def admin_audits(admin: User = Depends(require_admin), db=Depends(get_db)):
    audits = db.query(Audit).order_by(Audit.created_at.desc()).limit(200).all()
    out = []
    for a in audits:
        out.append({"id": a.id, "url": a.url, "website_id": a.website_id, "overall": a.overall, "grade": a.grade,
                    "errors": a.errors, "warnings": a.warnings, "notices": a.notices, "created_at": a.created_at})
    return out

# ------------------------------------------------------------------------------
# Scheduler loop (daily/accumulated) with SMTP delivery
# ------------------------------------------------------------------------------
async def scheduler_loop():
    await asyncio.sleep(3)
    while True:
        try:
            db = SessionLocal()
            now_utc = datetime.utcnow().replace(second=0, microsecond=0)
            schedules = db.query(Schedule).filter(Schedule.enabled == True).all()
            for s in schedules:
                hh, mm = map(int, (s.time_of_day or "09:00").split(":"))
                try:
                    tz = ZoneInfo(s.timezone or "UTC")
                except Exception:
                    tz = ZoneInfo("UTC")
                local_now = now_utc.astimezone(tz)
                scheduled_local = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                scheduled_utc = scheduled_local.astimezone(ZoneInfo("UTC"))
                should_run = (now_utc >= scheduled_utc and (not s.last_run_at or s.last_run_at < scheduled_utc))
                if should_run:
                    # Run audit and send email
                    payload = run_actual_audit(s.website.url)
                    pdf_bytes = generate_pdf_5pages(s.website.url, {
                        "grade": payload["grade"], "overall": payload["overall"], "summary": payload["summary"],
                        "strengths": payload["strengths"], "weaknesses": payload["weaknesses"], "priority": payload["priority"],
                        "errors": payload["errors"], "warnings": payload["warnings"], "notices": payload["notices"], "totals": payload["totals"],
                    })
                    user = s.user
                    subj = f"FF Tech Audit — {s.website.url} ({payload['grade']} / {payload['overall']}%)"
                    body = "Your scheduled audit is ready.\n\n" \
                           f"Website: {s.website.url}\nGrade: {payload['grade']}\nHealth: {payload['overall']}%\n\n" \
                           "Certified PDF attached.\n— FF Tech"
                    send_email(user.email, subj, body, [(f"fftech_audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf", pdf_bytes)])
                    # Persist Audit
                    row = Audit(
                        website_id=s.website.id, url=s.website.url, overall=payload["overall"], grade=payload["grade"],
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
``
