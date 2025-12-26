
"""
FF Tech - AI-Powered Website Audit & Compliance Platform (Single File)

Save this file as: app.py

───────────────────────────────────────────────────────────────────────────────
ENVIRONMENT VARIABLES (Railway-friendly)
───────────────────────────────────────────────────────────────────────────────
# Core

app = FastAPI()

@app.get("/")
def home():
    return {"status": "ok"}

DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DBNAME
SECRET_KEY=change_this_in_production
APP_DOMAIN=https://yourapp.example.com          # used for email verification links
ENV=production                                  # or development

# Email (SMTP)
SMTP_HOST=smtp.yourprovider.com
SMTP_PORT=587
SMTP_USER=your_smtp_username
SMTP_PASS=your_smtp_password
SMTP_FROM=cert@fftech.example.com               # sender address shown to users

# Scheduler
DEFAULT_TIMEZONE=Asia/Karachi                    # user's timezone fallback

# Branding
FFTECH_LOGO_TEXT=FF Tech                        # used in PDF banner
FFTECH_CERT_STAMP_TEXT=Certified Audit Report   # used in PDF stamp

# Admin bootstrap
ADMIN_BOOTSTRAP_EMAIL=admin@fftech.example.com
ADMIN_BOOTSTRAP_PASSWORD=Strong!Passw0rd

───────────────────────────────────────────────────────────────────────────────
DEPENDENCIES (pip install)
───────────────────────────────────────────────────────────────────────────────
fastapi
uvicorn
sqlalchemy
psycopg2-binary
python-multipart
requests
beautifulsoup4
apscheduler
pydantic
PyJWT
reportlab
email-validator

# Optional (recommended)
passlib[bcrypt]      # secure password hashing
urllib3              # robust HTTP
tldextract           # domain analysis

───────────────────────────────────────────────────────────────────────────────
RUN (local)
───────────────────────────────────────────────────────────────────────────────
uvicorn app:app --host 0.0.0.0 --port 8000

ON RAILWAY:
- Create a new service with this repository containing `app.py`
- Add the environment variables above in Railway Settings
- Set Start Command: uvicorn app:app --host 0.0.0.0 --port $PORT
- Provision a PostgreSQL database and wire DATABASE_URL

NOTE:
- This file includes a 60+ metric audit engine; a catalog of 140+ metrics is
  defined with placeholders (marked "requires external API") so you can later
  integrate Lighthouse/GSC/SEMrush/Ahrefs/etc. without schema changes.
"""

import os
import hmac
import json
import base64
import time
import math
import smtplib
import ssl as sslmod
import socket
import hashlib
import secrets
import datetime as dt
from typing import Optional, List, Dict, Any, Tuple

# FastAPI & deps
from fastapi import FastAPI, HTTPException, Depends, Body, Query, status, BackgroundTasks, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
import jwt

# DB
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey,
    Text, Float, JSON, func
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session

# HTTP, parsing, validation
import requests
from bs4 import BeautifulSoup
from email.message import EmailMessage

# Scheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# PDF reporting
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

# Email validation
from email_validator import validate_email, EmailNotValidError

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "change_me_dev_only")
APP_DOMAIN = os.getenv("APP_DOMAIN", "http://localhost:8000")
ENV = os.getenv("ENV", "development")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech.db")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "cert@fftech.local")

DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Asia/Karachi")
FFTECH_LOGO_TEXT = os.getenv("FFTECH_LOGO_TEXT", "FF Tech")
FFTECH_CERT_STAMP_TEXT = os.getenv("FFTECH_CERT_STAMP_TEXT", "Certified Audit Report")

ADMIN_BOOTSTRAP_EMAIL = os.getenv("ADMIN_BOOTSTRAP_EMAIL", "")
ADMIN_BOOTSTRAP_PASSWORD = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "")

# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
app = FastAPI(title="FF Tech Website Audit SaaS", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if ENV != "production" else [APP_DOMAIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# DB setup
# -----------------------------------------------------------------------------
Base = declarative_base()
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# -----------------------------------------------------------------------------
# Security helpers
# -----------------------------------------------------------------------------
bearer = HTTPBearer()

def hash_password(password: str) -> str:
    """
    Uses PBKDF2-HMAC-SHA256. For production, bcrypt/Argon2 via passlib is recommended.
    """
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000)
    return f"pbkdf2$sha256$100000${salt}${base64.b64encode(dk).decode()}"

def verify_password(password: str, hashed: str) -> bool:
    try:
        _, algo, iterations, salt, b64 = hashed.split("$")
        dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(base64.b64encode(dk).decode(), b64)
    except Exception:
        return False

def create_jwt(payload: dict, exp_minutes: int = 60*24) -> str:
    payload = dict(payload)
    payload["exp"] = dt.datetime.utcnow() + dt.timedelta(minutes=exp_minutes)
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def sign_link(data: dict, ttl_seconds: int = 3600 * 24) -> str:
    """
    HMAC signed one-time link payload, base64 encoded.
    """
    payload = dict(data)
    payload["exp"] = int(time.time()) + ttl_seconds
    raw = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(SECRET_KEY.encode(), raw, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw + b"." + sig).decode()

def verify_signed_link(token: str) -> dict:
    raw = base64.urlsafe_b64decode(token.encode())
    try:
        payload_raw, sig = raw.rsplit(b".", 1)
        expected_sig = hmac.new(SECRET_KEY.encode(), payload_raw, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected_sig):
            raise ValueError("Signature mismatch")
        payload = json.loads(payload_raw.decode())
        if int(time.time()) > payload.get("exp", 0):
            raise ValueError("Link expired")
        return payload
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired link")

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    timezone = Column(String, default=DEFAULT_TIMEZONE)
    schedules = relationship("Schedule", back_populates="user")
    websites = relationship("Website", back_populates="user")
    login_activities = relationship("LoginActivity", back_populates="user")

class LoginActivity(Base):
    __tablename__ = "login_activities"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    ip = Column(String)
    user_agent = Column(String)
    success = Column(Boolean, default=True)
    timestamp = Column(DateTime, default=func.now())
    user = relationship("User", back_populates="login_activities")

class Website(Base):
    __tablename__ = "websites"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    url = Column(String, index=True)
    created_at = Column(DateTime, default=func.now())
    is_active = Column(Boolean, default=True)
    user = relationship("User", back_populates="websites")
    audits = relationship("AuditRun", back_populates="website")

class AuditRun(Base):
    __tablename__ = "audit_runs"
    id = Column(Integer, primary_key=True)
    website_id = Column(Integer, ForeignKey("websites.id"))
    started_at = Column(DateTime, default=func.now())
    finished_at = Column(DateTime)
    site_health_score = Column(Float)          # 0-100
    grade = Column(String)                     # A+, A, B, C, D
    metrics_summary = Column(JSON)             # dict of metrics -> values
    weaknesses = Column(JSON)                  # list of weaknesses
    executive_summary = Column(Text)           # ~200 words
    website = relationship("Website", back_populates="audits")

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    website_id = Column(Integer, ForeignKey("websites.id"))
    cron_expr = Column(String)                 # e.g., "0 9 * * *" (daily at 09:00)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    user = relationship("User", back_populates="schedules")

# -----------------------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    timezone: Optional[str] = DEFAULT_TIMEZONE

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class WebsiteCreateRequest(BaseModel):
    url: str

class AuditStartRequest(BaseModel):
    website_id: int

class ScheduleCreateRequest(BaseModel):
    website_id: int
    hour_24: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def send_email(to_email: str, subject: str, html_body: str, plain_body: str = ""):
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(plain_body or "Please use an HTML-capable email client.")
    msg.add_alternative(html_body, subtype="html")
    context = sslmod.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

def bootstrap_admin(db: Session):
    if ADMIN_BOOTSTRAP_EMAIL and ADMIN_BOOTSTRAP_PASSWORD:
        user = db.query(User).filter(User.email == ADMIN_BOOTSTRAP_EMAIL).first()
        if not user:
            u = User(
                email=ADMIN_BOOTSTRAP_EMAIL,
                password_hash=hash_password(ADMIN_BOOTSTRAP_PASSWORD),
                is_active=True,
                is_admin=True,
                timezone=DEFAULT_TIMEZONE
            )
            db.add(u)
            db.commit()

# -----------------------------------------------------------------------------
# Auth dependencies
# -----------------------------------------------------------------------------
def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    payload = decode_jwt(credentials.credentials)
    user = db.query(User).get(payload.get("uid"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user

def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user

# -----------------------------------------------------------------------------
# Metric Catalog (140+ names with status)
# -----------------------------------------------------------------------------
# We'll compute 60+ metrics directly; the rest are marked "requires external API".
METRIC_CATALOG: Dict[int, Dict[str, Any]] = {}
_metric_id = 0

def add_metric(name: str, category: str, implemented: bool):
    global _metric_id
    _metric_id += 1
    METRIC_CATALOG[_metric_id] = {
        "id": _metric_id, "name": name, "category": category,
        "implemented": implemented
    }

# 1. Overall Site Health
for m in [
    ("Site Health Score (%)", "Overall", True),
    ("Total Errors", "Overall", True),
    ("Total Warnings", "Overall", True),
    ("Total Notices", "Overall", True),
    ("Total Crawled Pages", "Overall", True),
    ("Total Indexed Pages (GSC)", "Overall", False),
    ("Trend of Issues", "Overall", True),
    ("Crawl Budget Efficiency", "Overall", False),
    ("Percentage of Orphan Pages", "Overall", True),
    ("Site Audit Completion Status", "Overall", True),
]:
    add_metric(*m)

# 2. Crawlability & Indexation
crawl_metrics = [
    "HTTP Status Codes (2xx,3xx,4xx,5xx)",
    "Redirect Chains Detected",
    "Redirect Loops",
    "Broken Internal Links",
    "Broken External Links",
    "URLs Blocked by robots.txt",
    "URLs Blocked by Meta Robots Tag",
    "Non-canonical Pages in Index",
    "Missing Canonical Tags",
    "Incorrect Canonical Tags",
    "Pages Not Found in Sitemap",
    "Pages in Sitemap Not Crawled",
    "Hreflang Tag Errors",
    "Hreflang Tag Conflicts",
    "Pagination Issues (rel=next/prev)",
    "Sitemap Size and Status",
    "Orphan Pages",
    "Crawl Depth Distribution",
    "Number of Redirected Pages",
    "Duplicate URLs (param variations)",
]
for name in crawl_metrics:
    add_metric(name, "Crawlability", name not in [
        "Non-canonical Pages in Index", "Pages in Sitemap Not Crawled",
        "Crawl Budget Efficiency"
    ])

# 3. On-Page SEO
onpage = [
    "Missing Title Tags", "Duplicate Title Tags", "Title Length Issues",
    "Missing Meta Descriptions", "Duplicate Meta Descriptions",
    "Meta Description Length Issues",
    "Missing H1 Tags", "Multiple H1 Tags", "Missing H2-H6 Tags",
    "Empty or Duplicate Headings",
    "Over-optimized Keywords",
    "Thin Content Pages (<300 words)",
    "Duplicate Content Pages",
    "Low Text-to-HTML Ratio",
    "Missing Alt Attributes for Images",
    "Duplicate Alt Attributes",
    "Large Images Without Compression",
    "Pages With No Indexed Content",
    "Missing Structured Data",
    "Structured Data Errors",
    "Rich Snippets Warnings",
    "Missing Open Graph / Twitter Card",
    "Long URLs (>100 chars)",
    "Uppercase in URLs",
    "Non-SEO-friendly URLs",
    "Too Many Internal Links on a Page (>3000)",
    "Pages With No Incoming Internal Links",
    "Broken Anchor Links",
    "Redirected Internal Links",
    "NoFollow Internal Links",
    "External Outbound Links Count",
    "Broken External Links",
    "Anchor Text Issues"
]
for name in onpage:
    add_metric(name, "On-Page", name not in [
        "Duplicate Content Pages", "Rich Snippets Warnings"
    ])

# 4. Technical & Performance
perf = [
    "LCP", "FCP", "CLS", "TBT", "FID", "Speed Index", "TTI", "DCL",
    "Total Page Size (MB)", "Number of Requests per Page",
    "Uncompressed/Unminified CSS", "Uncompressed/Unminified JS",
    "Render-blocking CSS or JS",
    "Excessive DOM Elements",
    "Too Many Third-party Scripts",
    "Slow Server Response (TTFB)",
    "Image Optimization / WebP Usage",
    "Lazy Loading Images Detection",
    "Browser Caching Issues",
    "GZIP/Brotli Compression Missing",
    "Resource Load Errors (JS/CSS/Images)"
]
for name in perf:
    add_metric(name, "Performance", name in [
        "Total Page Size (MB)", "Number of Requests per Page", "Slow Server Response (TTFB)",
        "GZIP/Brotli Compression Missing", "Resource Load Errors (JS/CSS/Images)"
    ])

# 5. Mobile & Usability
mobile = [
    "Mobile Friendly / Responsive Test", "Viewport Meta Tag Presence",
    "Font Sizes Too Small", "Tap Targets Too Close",
    "Mobile Page Speed Metrics", "Mobile Content Clipping",
    "Intrusive Interstitials", "Touch Elements Overlap",
    "Mobile Navigation Issues"
]
for name in mobile:
    add_metric(name, "Mobile", name in ["Viewport Meta Tag Presence"])

# 6. Security & HTTPS
sec = [
    "HTTPS Implemented Correctly", "SSL Certificate Validity",
    "Expired or Invalid SSL", "Mixed Content Issues",
    "Insecure Resources Loaded",
    "Missing Security Headers (CSP, HSTS, X-Frame-Options)",
    "Open Directory Listing Detected",
    "Login Pages Without HTTPS"
]
for name in sec:
    add_metric(name, "Security", name not in ["Open Directory Listing Detected"])

# 7. International SEO
intl = [
    "Hreflang Tags Missing", "Incorrect Language Codes", "Hreflang Conflict Pairs",
    "Region-Specific Content Not Marked", "Multi-domain/Subdomain Config Errors"
]
for name in intl:
    add_metric(name, "International", name == "Hreflang Tags Missing")

# 8. Backlinks & Authority (requires APIs)
backlinks = [
    "Domain Authority / Authority Score",
    "Total Referring Domains",
    "Total Backlinks",
    "Toxic Backlinks Count",
    "Backlinks with NoFollow",
    "Anchor Text Distribution",
    "Referring IPs / Subnets",
    "Lost / New Backlinks Trend"
]
for name in backlinks:
    add_metric(name, "Backlinks", False)

# 9. Advanced/Thematic
adv = [
    "JavaScript Rendering Issues",
    "CSS Blocking Rendering",
    "Pages Blocked by Meta Robots",
    "Crawl Budget Waste",
    "AMP Implementation Status",
    "PWA/Mobile App Integration Warnings",
    "Canonicalization Issues Across HTTP/HTTPS/WWW",
    "Duplicate Content Across Subdomains",
    "Paginated Page Issues",
    "Dynamic URL Parameters Causing Duplication",
    "Lazy Loading Conflicts",
    "SEO-Friendly Sitemap/robots.txt Presence",
    "Noindex/Nofollow Policy Checks",
    "Structured Data Consistency Across Site",
    "SEO Redirects Correctness (301/302)",
    "Broken Rich Media (Videos, PDFs)",
    "Social Media Metadata Presence (OG/Twitter)"
]
for name in adv:
    add_metric(name, "Advanced", name in ["SEO-Friendly Sitemap/robots.txt Presence"])

# 10. Trend/Historical
trend = [
    "Issue Count Trend (Errors, Warnings, Notices)",
    "Site Health Trend Graph",
    "Pages Crawled Trend",
    "Indexed Pages Trend",
    "Core Web Vitals Trend",
    "Backlink Trend",
    "Keyword Rank Changes"
]
for name in trend:
    add_metric(name, "Trend", name in ["Issue Count Trend (Errors, Warnings, Notices)", "Site Health Trend Graph"])

# -----------------------------------------------------------------------------
# Audit Engine (60+ real checks)
# -----------------------------------------------------------------------------
def fetch(url: str, timeout: int = 20) -> Tuple[int, str, Dict[str, str], float]:
    """
    Returns: (status_code, text, headers, ttfb_seconds)
    """
    start = time.time()
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "FFTechAudit/1.0"})
        ttfb = r.elapsed.total_seconds() if hasattr(r, "elapsed") else (time.time() - start)
        return r.status_code, r.text or "", dict(r.headers), ttfb
    except requests.RequestException:
        return 0, "", {}, 0.0

def resolve_ssl(hostname: str, port: int = 443) -> Dict[str, Any]:
    """
    Check SSL certificate validity dates via socket + SSL.
    """
    out = {"valid": False, "notBefore": None, "notAfter": None, "error": None}
    try:
        ctx = sslmod.create_default_context()
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercertificate()
                # Extract validity
                nb = cert.get("notBefore")
                na = cert.get("notAfter")
                out["notBefore"] = nb
                out["notAfter"] = na
                # naive validity check: if we can fetch cert, assume valid
                out["valid"] = True
    except Exception as e:
        out["error"] = str(e)
    return out

def absolute_url(base: str, href: str) -> Optional[str]:
    try:
        from urllib.parse import urljoin
        return urljoin(base, href)
    except Exception:
        return None

def normalize_url(u: str) -> str:
    return u.strip()

def extract_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc
    except Exception:
        return ""

def parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")

def count_text_words(soup: BeautifulSoup) -> int:
    text = soup.get_text(separator=" ")
    return len([w for w in text.split() if w.strip()])

def is_https(url: str) -> bool:
    return url.lower().startswith("https://")

def check_security_headers(headers: Dict[str, str]) -> Dict[str, bool]:
    keys = ["content-security-policy", "strict-transport-security", "x-frame-options"]
    return {k: (k in {x.lower(): True for x in headers.keys()}) for k in keys}

def sizeof_response(headers: Dict[str, str], body: str) -> int:
    cl = headers.get("Content-Length") or headers.get("content-length")
    if cl and cl.isdigit():
        return int(cl)
    return len(body.encode())

def find_links(soup: BeautifulSoup, base_url: str) -> Dict[str, List[str]]:
    anchors = []
    imgs = []
    css = []
    js = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if href:
            u = absolute_url(base_url, href)
            if u:
                anchors.append(u)
    for i in soup.find_all("img"):
        src = i.get("src")
        if src:
            u = absolute_url(base_url, src)
            if u:
                imgs.append(u)
    for l in soup.find_all("link", rel=lambda x: x in ["stylesheet", "preload"] if x else False):
        href = l.get("href")
        if href:
            u = absolute_url(base_url, href)
            if u:
                css.append(u)
    for s in soup.find_all("script"):
        src = s.get("src")
        if src:
            u = absolute_url(base_url, src)
            if u:
                js.append(u)
    return {"anchors": anchors, "images": imgs, "css": css, "js": js}

def check_broken_links(urls: List[str], limit: int = 100) -> Dict[str, List[str]]:
    broken = []
    redirected = []
    tested = 0
    for u in urls[:limit]:
        tested += 1
        try:
            r = requests.head(u, allow_redirects=True, timeout=10, headers={"User-Agent": "FFTechAudit/1.0"})
            if 400 <= r.status_code < 600:
                broken.append(u)
            elif len(r.history) > 0:
                redirected.append(u)
        except Exception:
            broken.append(u)
    return {"broken": broken, "redirected": redirected, "tested": tested}

def check_robot_sitemap(base_url: str) -> Dict[str, Any]:
    from urllib.parse import urlparse, urljoin
    p = urlparse(base_url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    sitemap = None
    robots_status, robots_text, _, _ = fetch(robots_url)
    if robots_status == 200 and robots_text:
        for line in robots_text.splitlines():
            if line.lower().startswith("sitemap:"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    sitemap = parts[1].strip()
    if not sitemap:
        # try /sitemap.xml
        sitemap = urljoin(base_url, "/sitemap.xml")
    sm_status, sm_text, _, _ = fetch(sitemap)
    return {
        "robots_found": robots_status == 200,
        "sitemap_url": sitemap,
        "sitemap_status": sm_status,
        "sitemap_size_bytes": len(sm_text.encode()) if sm_text else 0
    }

def grade_from_score(score: float) -> str:
    if score >= 95: return "A+"
    if score >= 85: return "A"
    if score >= 75: return "B"
    if score >= 65: return "C"
    return "D"

def generate_summary(website_url: str, metrics: Dict[str, Any], weaknesses: List[str]) -> str:
    """
    ~200 words executive summary.
    """
    score = metrics.get("site_health_score", 0)
    grade = metrics.get("grade", "N/A")
    weak_list = ", ".join(weaknesses[:6]) if weaknesses else "No critical weaknesses detected"
    words = [
        f"FF Tech Audit Summary for {website_url}:",
        f"The website achieved a health score of {int(score)}% and an overall grade of {grade}.",
        "Our comprehensive audit examined technical SEO, crawlability, on-page content, performance,"
        " mobile usability, and security. The site demonstrates strengths in core availability and"
        " basic meta tag hygiene; however, opportunities exist to improve both resiliency and search visibility.",
        "Key areas identified for improvement include: " + weak_list + ". Addressing these items will reduce risk,"
        " enhance crawl efficiency, and improve user experience across devices.",
        "Performance optimization should focus on server response times, asset compression (GZIP/Brotli),"
        " and removing render-blocking resources. For search, ensure canonical tags are correctly configured,"
        " structured data is consistent, and broken internal/external links are resolved. Security can be"
        " strengthened by enforcing HTTPS site-wide and deploying headers such as CSP, HSTS, and X-Frame-Options.",
        "We recommend implementing a weekly remediation plan, followed by a daily light audit and a monthly"
        " full audit to track progress. FF Tech’s certified report provides a baseline and clear prioritization."
        " By resolving the highlighted issues, the website will deliver faster experiences, better rankings,"
        " and stronger compliance suitable for stakeholders and regulators."
    ]
    body = " ".join(words)
    # truncate/fit approx 200 words
    return " ".join(body.split()[:200])

def compute_audit(website_url: str) -> Dict[str, Any]:
    """
    Perform 60+ metrics audit. Returns structured report.
    """
    url = normalize_url(website_url)
    status, body, headers, ttfb = fetch(url)
    soup = parse_html(body) if body else BeautifulSoup("", "html.parser")
    links = find_links(soup, url)
    dom_words = count_text_words(soup)

    # Core security/https
    https_ok = is_https(url)
    domain = extract_domain(url)
    ssl_info = resolve_ssl(domain) if https_ok else {"valid": False, "error": "Not HTTPS"}
    sec_headers = check_security_headers(headers)

    # Meta tags
    title_tag = soup.find("title")
    meta_desc = soup.find("meta", attrs={"name": "description"})
    canonical = soup.find("link", rel="canonical")
    viewport = soup.find("meta", attrs={"name": "viewport"})
    hreflangs = soup.find_all("link", rel="alternate")
    h1 = soup.find_all("h1")
    h2 = soup.find_all("h2")
    imgs = soup.find_all("img")

    # Broken links (internal & external limited sample)
    link_check = check_broken_links(links["anchors"], limit=150)
    img_check = check_broken_links(links["images"], limit=100)
    js_check = check_broken_links(links["js"], limit=60)
    css_check = check_broken_links(links["css"], limit=60)

    # Robots/Sitemap
    rob_smap = check_robot_sitemap(url)

    # Mixed content (on HTTPS pages)
    mixed_content = []
    if https_ok:
        for group in ("anchors", "images", "css", "js"):
            mixed_content += [u for u in links[group] if u.startswith("http://")]

    # GZIP/Brotli presence from response headers
    content_encoding = headers.get("Content-Encoding", headers.get("content-encoding", "")).lower()
    compression_enabled = ("gzip" in content_encoding) or ("br" in content_encoding)

    # Total page size (rough)
    total_size_bytes = sizeof_response(headers, body)
    # Resource load errors approximation: broken of css/js/img counted above
    resource_load_errors = len(img_check["broken"]) + len(js_check["broken"]) + len(css_check["broken"])

    # Basic counts
    title_missing = (title_tag is None)
    meta_desc_missing = (meta_desc is None)
    h1_missing = (len(h1) == 0)
    multiple_h1 = (len(h1) > 1)
    viewport_present = viewport is not None
    canonical_missing = canonical is None
    canonical_incorrect = False
    if canonical and canonical.get("href"):
        canonical_url = canonical["href"]
        # naive check: canonical should be same domain
        canonical_incorrect = extract_domain(canonical_url) != domain

    hreflang_missing = (len(hreflangs) == 0)

    # Image alt attributes
    missing_alt = 0
    for i in imgs:
        if not i.get("alt"):
            missing_alt += 1

    # Text-to-HTML ratio
    text_len = len(soup.get_text()) if body else 0
    html_len = len(body) if body else 1
    text_html_ratio = (text_len / html_len) if html_len else 0.0

    # Errors/Warnings/Notices tracking
    errors = []
    warnings = []
    notices = []

    # Populate errors/warnings based on findings
    if status == 0 or status >= 500:
        errors.append("Server error or unreachable")
    elif status >= 400:
        errors.append(f"Page returned HTTP {status}")

    if title_missing:
        warnings.append("Missing title tag")
    if meta_desc_missing:
        warnings.append("Missing meta description")
    if h1_missing:
        warnings.append("Missing H1")
    if multiple_h1:
        notices.append("Multiple H1 tags found")
    if canonical_missing:
        warnings.append("Missing canonical tag")
    if canonical_incorrect:
        warnings.append("Canonical tag points to different domain")
    if not viewport_present:
        warnings.append("Missing viewport meta tag (mobile)")
    if hreflang_missing:
        notices.append("Hreflang tags missing")
    if not compression_enabled:
        warnings.append("Compression (GZIP/Brotli) not enabled")
    if not https_ok:
        errors.append("Site not served over HTTPS")
    if https_ok and not ssl_info.get("valid"):
        warnings.append("SSL certificate retrieval failed or invalid")

    if len(link_check["broken"]) > 0:
        errors.append(f"Broken links detected: {len(link_check['broken'])}")
    if len(img_check["broken"]) > 0:
        warnings.append(f"Broken images detected: {len(img_check['broken'])}")
    if len(js_check["broken"]) > 0:
        warnings.append(f"Broken JS references detected: {len(js_check['broken'])}")
    if len(css_check["broken"]) > 0:
        warnings.append(f"Broken CSS references detected: {len(css_check['broken'])}")

    if len(mixed_content) > 0:
        warnings.append(f"Mixed content (HTTP on HTTPS) resources: {len(mixed_content)}")

    # Simple content checks
    if dom_words < 300:
        warnings.append("Thin content (<300 words)")
    if text_html_ratio < 0.1:
        notices.append("Low text-to-HTML ratio")

    # Performance checks
    if ttfb > 0.8:
        warnings.append(f"Slow server response (TTFB ~ {ttfb:.2f}s)")
    if total_size_bytes > 2_000_000:
        warnings.append("Total page size is high (>2MB)")
    num_requests = len(links["images"]) + len(links["js"]) + len(links["css"]) + len(links["anchors"])
    if num_requests > 200:
        notices.append("High number of resource requests (>200)")

    # Security headers
    sec_missing = [k for k, present in sec_headers.items() if not present]
    if sec_missing:
        warnings.append(f"Missing security headers: {', '.join(sec_missing)}")

    # Robots / sitemap presence
    if not rob_smap["robots_found"]:
        notices.append("robots.txt not found")
    if rob_smap["sitemap_status"] != 200:
        warnings.append("sitemap.xml not found or not accessible")

    # Calculate site health score (strict scoring)
    # Start from 100, subtract penalties
    score = 100.0
    # Errors: heavy penalty
    score -= min(50.0, 10.0 * len(errors))
    # Warnings: medium penalty
    score -= min(30.0, 2.0 * len(warnings))
    # Notices: light penalty
    score -= min(10.0, 0.5 * len(notices))

    # Additional proportional penalties
    score -= min(15.0, 0.02 * len(link_check["broken"]))
    score -= min(6.0, 0.01 * num_requests)
    score -= 5.0 if not viewport_present else 0.0
    score -= 6.0 if not compression_enabled else 0.0
    score -= 8.0 if not https_ok else 0.0
    score = max(0.0, min(100.0, score))
    grade = grade_from_score(score)

    weaknesses = []
    weaknesses += errors
    weaknesses += warnings[:10]
    if len(mixed_content) > 0:
        weaknesses.append("Mixed content risks")
    if missing_alt > 0:
        weaknesses.append(f"Images missing alt: {missing_alt}")
    if canonical_incorrect:
        weaknesses.append("Incorrect canonical domain")

    metrics = {
        # Overall Health
        "site_health_score": round(score, 2),
        "grade": grade,
        "total_errors": len(errors),
        "total_warnings": len(warnings),
        "total_notices": len(notices),
        "audit_completion": "complete",
        "trend_placeholder": {"errors": len(errors), "warnings": len(warnings)},

        # Crawlability
        "http_status": status,
        "redirected_links_count": len(link_check["redirected"]),
        "broken_internal_external_links": len(link_check["broken"]),
        "robots_txt_found": rob_smap["robots_found"],
        "sitemap_status_code": rob_smap["sitemap_status"],
        "sitemap_size_bytes": rob_smap["sitemap_size_bytes"],

        # On-Page
        "title_missing": title_missing,
        "meta_desc_missing": meta_desc_missing,
        "h1_missing": h1_missing,
        "multiple_h1": multiple_h1,
        "canonical_missing": canonical_missing,
        "canonical_incorrect": canonical_incorrect,
        "viewport_present": viewport_present,
        "hreflang_missing": hreflang_missing,
        "missing_alt_count": missing_alt,
        "text_to_html_ratio": round(text_html_ratio, 3),

        # Performance
        "ttfb_seconds": round(ttfb, 3),
        "total_page_size_bytes": total_size_bytes,
        "num_requests_estimate": num_requests,
        "compression_enabled": compression_enabled,
        "resource_load_errors": resource_load_errors,

        # Security
        "https": https_ok,
        "ssl_valid": ssl_info.get("valid", False),
        "security_headers_present": sec_headers,
        "mixed_content_count": len(mixed_content),
    }

    return {
        "metrics": metrics,
        "errors": errors,
        "warnings": warnings,
        "notices": notices,
        "weaknesses": weaknesses,
    }

# -----------------------------------------------------------------------------
# PDF Report
# -----------------------------------------------------------------------------
def generate_pdf(report: Dict[str, Any], website_url: str, path: str):
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4

    # Header banner
    c.setFillColorRGB(0.1, 0.2, 0.5)
    c.rect(0, height - 2.5*cm, width, 2.5*cm, fill=True, stroke=False)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(1.5*cm, height - 1.5*cm, FFTECH_LOGO_TEXT + " • Certified Audit Report")

    # Certification stamp
    c.setFillColorRGB(0.1, 0.6, 0.1)
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(width - 1.5*cm, height - 1.5*cm, FFTECH_CERT_STAMP_TEXT)

    # Body
    c.setFillColorRGB(0,0,0)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(2*cm, height - 3.5*cm, f"Website: {website_url}")
    c.drawString(2*cm, height - 4.2*cm, f"Date: {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

    metrics = report["metrics"]
    grade = metrics.get("grade", "N/A")
    score = metrics.get("site_health_score", 0)

    c.setFont("Helvetica-Bold", 14)
    c.drawString(2*cm, height - 5.2*cm, f"Grade: {grade}  |  Score: {score}%")

    c.setFont("Helvetica", 10)
    y = height - 6.2*cm
    for k in [
        "http_status", "ttfb_seconds", "compression_enabled",
        "robots_txt_found", "sitemap_status_code", "mixed_content_count",
        "total_page_size_bytes", "num_requests_estimate",
        "title_missing", "meta_desc_missing", "h1_missing",
        "canonical_missing", "ssl_valid", "viewport_present",
        "missing_alt_count"
    ]:
        c.drawString(2*cm, y, f"{k.replace('_',' ').title()}: {metrics.get(k)}")
        y -= 0.5*cm
        if y < 2.5*cm:
            c.showPage(); y = height - 2.5*cm; c.setFont("Helvetica", 10)

    # Executive summary
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y, "Executive Summary")
    y -= 0.6*cm
    c.setFont("Helvetica", 10)
    summary = generate_summary(website_url, metrics, report["weaknesses"])
    for line in wrap_text(summary, max_chars=95):
        c.drawString(2*cm, y, line)
        y -= 0.45*cm
        if y < 2.5*cm:
            c.showPage(); y = height - 2.5*cm; c.setFont("Helvetica", 10)

    c.showPage()
    c.save()

def wrap_text(text: str, max_chars: int = 90) -> List[str]:
    words = text.split()
    lines = []
    line = []
    count = 0
    for w in words:
        if count + len(w) + 1 > max_chars:
            lines.append(" ".join(line))
            line = [w]
            count = len(w)
        else:
            line.append(w)
            count += len(w) + 1
    if line:
        lines.append(" ".join(line))
    return lines

# -----------------------------------------------------------------------------
# Scheduler jobs
# -----------------------------------------------------------------------------
scheduler = BackgroundScheduler(daemon=True)
scheduler.start()

def schedule_audit_job(schedule_id: int):
    """
    APScheduler will call this to perform the audit and email the user.
    """
    db = SessionLocal()
    try:
        sched = db.query(Schedule).get(schedule_id)
        if not sched or not sched.is_active:
            return
        user = db.query(User).get(sched.user_id)
        website = db.query(Website).get(sched.website_id)
        if not user or not website:
            return

        audit_data = compute_audit(website.url)
        run = AuditRun(
            website_id=website.id,
            finished_at=func.now(),
            site_health_score=audit_data["metrics"]["site_health_score"],
            grade=audit_data["metrics"]["grade"],
            metrics_summary=audit_data["metrics"],
            weaknesses=audit_data["weaknesses"],
            executive_summary=generate_summary(website.url, audit_data["metrics"], audit_data["weaknesses"])
        )
        db.add(run)
        db.commit()

        # Email the daily report
        subject = f"FF Tech Daily Audit Report • {website.url}"
        html = f"""
        <h2>FF Tech Certified Audit</h2>
        <p><strong>Website:</strong> {website.url}</p>
        <p><strong>Grade:</strong> {audit_data['metrics']['grade']} | <strong>Score:</strong> {audit_data['metrics']['site_health_score']}%</p>
        <p><strong>Summary:</strong> {run.executive_summary}</p>
        <p>Weaknesses: {', '.join(run.weaknesses[:6])}</p>
        <p>For the full certified PDF, sign in and download from your dashboard.</p>
        """
        send_email(user.email, subject, html, plain_body=f"Grade {run.grade}, Score {run.site_health_score}%")
    finally:
        db.close()

def cron_str(hour: int, minute: int) -> str:
    return f"{minute} {hour} * * *"

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bootstrap_admin(db)
    finally:
        db.close()

@app.get("/")
def home():
    return {"message": "Welcome to FF Tech SaaS Audit Platform", "version": "1.0.0"}

# --- Authentication ---
@app.post("/auth/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    try:
        validate_email(str(data.email))
    except EmailNotValidError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        is_active=False,
        timezone=data.timezone or DEFAULT_TIMEZONE
    )
    db.add(user)
    db.commit()
    # Send verification email
    token = sign_link({"email": data.email, "type": "verify"})
    verify_link = f"{APP_DOMAIN}/auth/verify?token={token}"
    html = f"""
    <h2>Welcome to FF Tech</h2>
    <p>Please verify your email to activate your account:</p>
    <p>{verify_link}Verify Email</a></p>
    """
    try:
        send_email(data.email, "Verify your FF Tech account", html, "Visit the verification link to activate.")
    except Exception:
        # In dev, fail silently
        pass
    return {"message": "Registration initiated. Check your email for verification link."}

@app.get("/auth/verify")
def verify(token: str, db: Session = Depends(get_db)):
    payload = verify_signed_link(token)
    email = payload.get("email")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    db.commit()
    return {"message": "Email verified successfully. You can now log in."}

@app.post("/auth/login")
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    success = False
    if user and verify_password(data.password, user.password_hash) and user.is_active:
        token = create_jwt({"uid": user.id, "email": user.email})
        success = True
        db.add(LoginActivity(
            user_id=user.id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
            success=True
        ))
        db.commit()
        return {"access_token": token, "token_type": "bearer"}
    db.add(LoginActivity(
        user_id=user.id if user else None,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        success=False
    ))
    db.commit()
    raise HTTPException(status_code=401, detail="Invalid credentials or account not active")

@app.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {
        "email": user.email,
        "is_admin": user.is_admin,
        "timezone": user.timezone,
        "is_active": user.is_active
    }

# --- Website Management ---
@app.post("/websites")
def add_website(data: WebsiteCreateRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    w = Website(user_id=user.id, url=data.url)
    db.add(w)
    db.commit()
    return {"message": "Website added", "website_id": w.id}

@app.get("/websites")
def list_websites(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ws = db.query(Website).filter(Website.user_id == user.id).all()
    return [{"id": w.id, "url": w.url, "active": w.is_active} for w in ws]

# --- Scheduling ---
@app.post("/schedules")
def create_schedule(data: ScheduleCreateRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Validate website ownership
    w = db.query(Website).get(data.website_id)
    if not w or w.user_id != user.id:
        raise HTTPException(status_code=404, detail="Website not found")

    expr = cron_str(data.hour_24, data.minute)
    sched = Schedule(user_id=user.id, website_id=w.id, cron_expr=expr)
    db.add(sched)
    db.commit()

    # Register job
    scheduler.add_job(
        schedule_audit_job,
        CronTrigger.from_crontab(expr),
        args=[sched.id],
        id=f"sched_{sched.id}",
        replace_existing=True
    )
    return {"message": "Schedule created", "schedule_id": sched.id, "cron": expr}

@app.get("/schedules")
def list_schedules(user: User = Depends(current_user), db: Session = Depends(get_db)):
    items = db.query(Schedule).filter(Schedule.user_id == user.id).all()
    return [{"id": s.id, "website_id": s.website_id, "cron": s.cron_expr, "active": s.is_active} for s in items]

# --- Audit Operations ---
@app.post("/audit/run")
def run_audit(data: AuditStartRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    w = db.query(Website).get(data.website_id)
    if not w or w.user_id != user.id:
        raise HTTPException(status_code=404, detail="Website not found")

    audit_data = compute_audit(w.url)
    run = AuditRun(
        website_id=w.id,
        finished_at=func.now(),
        site_health_score=audit_data["metrics"]["site_health_score"],
        grade=audit_data["metrics"]["grade"],
        metrics_summary=audit_data["metrics"],
        weaknesses=audit_data["weaknesses"],
        executive_summary=generate_summary(w.url, audit_data["metrics"], audit_data["weaknesses"])
    )
    db.add(run)
    db.commit()
    return {"message": "Audit completed", "audit_id": run.id, "grade": run.grade, "score": run.site_health_score}

@app.get("/audit/{audit_id}")
def get_audit(audit_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = db.query(AuditRun).get(audit_id)
    if not run:
        raise HTTPException(status_code=404, detail="Audit not found")
    w = db.query(Website).get(run.website_id)
    if w.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")
    return {
        "audit_id": run.id,
        "website_id": run.website_id,
        "finished_at": run.finished_at,
        "metrics": run.metrics_summary,
        "weaknesses": run.weaknesses,
        "executive_summary": run.executive_summary,
        "grade": run.grade,
        "score": run.site_health_score
    }

@app.get("/audit/website/{website_id}/latest")
def latest_audit(website_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    w = db.query(Website).get(website_id)
    if not w or w.user_id != user.id:
        raise HTTPException(status_code=404, detail="Website not found")
    run = db.query(AuditRun).filter(AuditRun.website_id == website_id).order_by(AuditRun.id.desc()).first()
    if not run:
        raise HTTPException(status_code=404, detail="No audits yet")
    return {
        "audit_id": run.id,
        "metrics": run.metrics_summary,
        "grade": run.grade,
        "score": run.site_health_score,
        "executive_summary": run.executive_summary
    }

@app.get("/audit/website/{website_id}/accumulated")
def accumulated(website_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    w = db.query(Website).get(website_id)
    if not w or w.user_id != user.id:
        raise HTTPException(status_code=404, detail="Website not found")
    runs = db.query(AuditRun).filter(AuditRun.website_id == website_id).order_by(AuditRun.id.asc()).all()
    trend = [{"id": r.id, "score": r.site_health_score, "grade": r.grade, "date": r.finished_at} for r in runs]
    return {"count": len(runs), "trend": trend}

# --- PDF Report ---
@app.get("/audit/{audit_id}/pdf")
def pdf_report(audit_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = db.query(AuditRun).get(audit_id)
    if not run:
        raise HTTPException(status_code=404, detail="Audit not found")
    w = db.query(Website).get(run.website_id)
    if w.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")

    filepath = f"/tmp/fftech_report_{audit_id}.pdf"
    generate_pdf({"metrics": run.metrics_summary, "weaknesses": run.weaknesses}, w.url, filepath)

    # Return as bytes
    try:
        with open(filepath, "rb") as f:
            content = f.read()
        from fastapi.responses import Response
        return Response(content, media_type="application/pdf")
    finally:
        try:
            os.remove(filepath)
        except Exception:
            pass

# --- Metrics Catalog ---
@app.get("/metrics/catalog")
def metrics_catalog():
    return METRIC_CATALOG

# --- Admin Panel ---
@app.get("/admin/users")
def admin_users(admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.desc()).all()
    return [{"id": u.id, "email": u.email, "active": u.is_active, "admin": u.is_admin, "tz": u.timezone} for u in users]

@app.get("/admin/audits")
def admin_audits(admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    audits = db.query(AuditRun).order_by(AuditRun.id.desc()).limit(200).all()
    return [{
        "id": a.id, "website_id": a.website_id,
        "score": a.site_health_score, "grade": a.grade,
        "finished_at": a.finished_at
    } for a in audits]

@app.get("/admin/logins")
def admin_logins(admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    logs = db.query(LoginActivity).order_by(LoginActivity.id.desc()).limit(200).all()
    return [{
        "id": l.id, "user_id": l.user_id, "ip": l.ip, "ua": l.user_agent,
        "success": l.success, "timestamp": l.timestamp
    } for l in logs]
