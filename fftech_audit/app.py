
import os
import io
import re
import ssl
import json
import time
import base64
import hmac
import hashlib
import random
import string
import datetime
import requests
from typing import Dict, Any, List, Tuple

from urllib.parse import urlparse, urljoin

from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, inspect, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# --- PDF (ReportLab) ---
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
APP_NAME = "FF Tech AI Website Audit SaaS"
PORT = int(os.getenv("PORT", "8080"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech_audit.db")
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_SECRET_32+CHARS")

# SMTP (optional; used for magic link emails & scheduled PDF emails)
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587")) if os.getenv("SMTP_PORT") else None
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@fftech.example")

FREE_AUDIT_LIMIT = 10
SCHEDULER_SLEEP = int(os.getenv("SCHEDULER_INTERVAL", "60"))  # seconds

# ------------------------------------------------------------------------------
# FastAPI App & CORS
# ------------------------------------------------------------------------------
app = FastAPI(title=APP_NAME, version="3.2.0", description="FF Tech AI Website Audit SaaS - single-file implementation")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
security = HTTPBearer()

# ------------------------------------------------------------------------------
# Database (SQLAlchemy) + pool tuning to avoid overflow
# ------------------------------------------------------------------------------
Base = declarative_base()
_engine_kwargs = {
    "pool_pre_ping": True,
    "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
}
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------------------------------------------------------------------
# Models
# ------------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    verified = Column(Boolean, default=False)
    plan = Column(String(32), default="free")  # free|pro|enterprise
    audits_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    audits = relationship("Audit", back_populates="user")

class Audit(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    url = Column(String(2048), nullable=False)
    metrics_json = Column(Text)
    score = Column(Integer)
    grade = Column(String(4))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user = relationship("User", back_populates="audits")

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    url = Column(String(2048), nullable=False)
    frequency = Column(String(32), default="weekly")   # daily|weekly|monthly
    enabled = Column(Boolean, default=True)
    next_run_at = Column(DateTime, default=datetime.datetime.utcnow)

class MagicLink(Base):
    __tablename__ = "magic_links"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), index=True, nullable=False)
    token = Column(String(512), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class EmailCode(Base):
    __tablename__ = "email_codes"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), index=True, nullable=False)
    code = Column(String(12), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

# ------------------------------------------------------------------------------
# Auto-remediation: ensure schedules table has required columns (for existing DBs)
# ------------------------------------------------------------------------------
def ensure_schedule_columns():
    dialect = engine.dialect.name
    insp = inspect(engine)
    tables = insp.get_table_names()
    if "schedules" not in tables:
        return
    existing_cols = {col["name"] for col in insp.get_columns("schedules")}
    required = {
        "url": ("VARCHAR(2048)" if dialect == "postgresql" else "TEXT"),
        "frequency": ("VARCHAR(32)" if dialect == "postgresql" else "TEXT"),
        "enabled": ("BOOLEAN" if dialect == "postgresql" else "INTEGER"),
        "next_run_at": ("TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME"),
    }
    ddls = []
    for col_name, col_type in required.items():
        if col_name not in existing_cols:
            if dialect == "postgresql":
                default_clause = ""
                if col_name == "frequency":
                    default_clause = " DEFAULT 'weekly'"
                elif col_name == "enabled":
                    default_clause = " DEFAULT TRUE"
                elif col_name == "next_run_at":
                    default_clause = " DEFAULT NOW()"
                ddl = f"ALTER TABLE schedules ADD COLUMN IF NOT EXISTS {col_name} {col_type}{default_clause};"
            elif dialect == "sqlite":
                default_clause = ""
                if col_name == "frequency":
                    default_clause = " DEFAULT 'weekly'"
                elif col_name == "enabled":
                    default_clause = " DEFAULT 1"
                ddl = f"ALTER TABLE schedules ADD COLUMN {col_name} {col_type}{default_clause};"
            else:
                ddl = f"ALTER TABLE schedules ADD COLUMN {col_name} {col_type};"
            ddls.append(ddl)
    if ddls:
        with engine.begin() as conn:
            for ddl in ddls:
                try:
                    conn.execute(text(ddl))
                except Exception as e:
                    print(f"[DB] ensure_schedule_columns: DDL failed '{ddl}': {e}")

try:
    ensure_schedule_columns()
except Exception as e:
    print(f"[DB] ensure_schedule_columns failed: {e}")

# ------------------------------------------------------------------------------
# Security / Token
# ------------------------------------------------------------------------------
def now_utc() -> datetime.datetime:
    return datetime.datetime.utcnow()

def base64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")

def base64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "==")

def generate_token(payload: Dict[str, Any], exp_minutes: int = 60*24*30) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = dict(payload)
    payload["exp"] = int(time.time()) + exp_minutes * 60
    h_b64 = base64url(json.dumps(header).encode())
    p_b64 = base64url(json.dumps(payload).encode())
    signing_input = f"{h_b64}.{p_b64}".encode()
    sig = hmac.new(SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
    s_b64 = base64url(sig)
    return f"{h_b64}.{p_b64}.{s_b64}"

def verify_session_token(token: str) -> Dict[str, Any]:
    try:
        h_b64, p_b64, s_b64 = token.split(".")
        signing_input = f"{h_b64}.{p_b64}".encode()
        expected = hmac.new(SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
        given = base64url_decode(s_b64)
        if not hmac.compare_digest(expected, given):
            raise ValueError("Bad signature")
        payload = json.loads(base64url_decode(p_b64))
        if int(time.time()) > payload.get("exp", 0):
            raise ValueError("Expired")
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

# ------------------------------------------------------------------------------
# Email (Magic Link + OTP + PDF)
# ------------------------------------------------------------------------------
def send_magic_link(email: str, request: Request, db):
    email = email.lower().strip()
    token = generate_token({"email": email, "purpose": "magic"}, exp_minutes=30)
    ml = MagicLink(email=email, token=token, expires_at=now_utc() + datetime.timedelta(minutes=30), used=False)
    db.add(ml); db.commit()
    verify_url = f"{str(request.base_url).rstrip('/')}/auth/verify-link?token={token}"
    print(f"[DEV] Magic link for {email}: {verify_url}")
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS and SMTP_FROM):
        return
    subject = "FF Tech Login Link"
    body = f"Click to log in:\n\n{verify_url}\n\nThis link expires in 30 minutes."
    message = f"From: {SMTP_FROM}\r\nTo: {email}\r\nSubject: {subject}\r\n\r\n{body}"
    import smtplib
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context); server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_FROM, [email], message)

def verify_magic_link_and_issue_token(token: str, db) -> str:
    try:
        h_b64, p_b64, s_b64 = token.split(".")
        signing_input = f"{h_b64}.{p_b64}".encode()
        expected = hmac.new(SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
        given = base64url_decode(s_b64)
        if not hmac.compare_digest(expected, given):
            raise ValueError("Bad signature")
        payload = json.loads(base64url_decode(p_b64))
        if int(time.time()) > payload.get("exp", 0):
            raise ValueError("Expired")
        if payload.get("purpose") != "magic":
            raise ValueError("Invalid purpose")
        email = payload.get("email")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid magic link: {e}")
    ml = db.query(MagicLink).filter(MagicLink.token == token).first()
    if not ml or ml.used or ml.expires_at < now_utc():
        raise HTTPException(status_code=400, detail="Magic link invalid or expired")
    ml.used = True
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, verified=True, plan="free"); db.add(user)
    else:
        user.verified = True
    db.commit()
    return generate_token({"email": email, "purpose": "session"})

def send_verification_code(email: str, request: Request, db):
    code = "".join(random.choices("0123456789", k=6))
    rec = EmailCode(email=email.lower().strip(), code=code, expires_at=now_utc() + datetime.timedelta(minutes=30), used=False)
    db.add(rec); db.commit()
    print(f"[DEV] Verification code for {email}: {code}")
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS and SMTP_FROM):
        return
    subject = "Your FF Tech verification code"
    body = f"Your verification code is: {code}\n\nIt expires in 30 minutes."
    message = f"From: {SMTP_FROM}\r\nTo: {email}\r\nSubject: {subject}\r\n\r\n{body}"
    import smtplib
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context); server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_FROM, [email], message)

def verify_email_code_and_issue_token(email: str, code: str, db) -> str:
    rec = db.query(EmailCode).filter(EmailCode.email == email.lower().strip(), EmailCode.code == code).order_by(EmailCode.created_at.desc()).first()
    if not rec: raise HTTPException(status_code=400, detail="Invalid code")
    if rec.used: raise HTTPException(status_code=400, detail="Code already used")
    if rec.expires_at < now_utc(): raise HTTPException(status_code=400, detail="Code expired")
    rec.used = True
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user:
        user = User(email=email.lower().strip(), verified=True, plan="free"); db.add(user)
    else:
        user.verified = True
    db.commit()
    return generate_token({"email": email.lower().strip(), "purpose": "session"})

def send_email_with_pdf(email: str, subject: str, body: str, pdf_bytes: bytes, filename: str = "FFTech_Audit.pdf"):
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS and SMTP_FROM):
        print("[DEV] SMTP not configured; skipping email send.")
        return
    boundary = "===============%s==" % ("".join(random.choices(string.ascii_letters+string.digits, k=24)))
    header = [
        f"From: {SMTP_FROM}",
        f"To: {email}",
        f"Subject: {subject}",
        "MIME-Version: 1.0",
        f"Content-Type: multipart/mixed; boundary=\"{boundary}\"",
        "",
        f"--{boundary}",
        "Content-Type: text/plain; charset=\"utf-8\"",
        "",
        body,
        f"--{boundary}",
        f"Content-Type: application/pdf; name=\"{filename}\"",
        "Content-Transfer-Encoding: base64",
        f"Content-Disposition: attachment; filename=\"{filename}\"",
        "",
        base64.b64encode(pdf_bytes).decode(),
        f"--{boundary}--",
        ""
    ]
    message = "\r\n".join(header)
    import smtplib
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context); server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_FROM, [email], message)

# ------------------------------------------------------------------------------
# Audit Engine (200 metrics + scoring)
# ------------------------------------------------------------------------------
METRIC_DESCRIPTORS: Dict[int, Dict[str, Any]] = {}

def register_metrics():
    sections = {
        "A": [
            "Overall Site Health Score (%)","Website Grade (A+ to D)","Executive Summary (200 Words)",
            "Strengths Highlight Panel","Weak Areas Highlight Panel","Priority Fixes Panel",
            "Visual Severity Indicators","Category Score Breakdown","Industry-Standard Presentation",
            "Print / Certified Export Readiness"
        ],
        "B": [
            "Site Health Score","Total Errors","Total Warnings","Total Notices","Total Crawled Pages",
            "Total Indexed Pages","Issues Trend","Crawl Budget Efficiency","Orphan Pages Percentage",
            "Audit Completion Status"
        ],
        "C": [
            "HTTP 2xx Pages","HTTP 3xx Pages","HTTP 4xx Pages","HTTP 5xx Pages","Redirect Chains",
            "Redirect Loops","Broken Internal Links","Broken External Links","robots.txt Blocked URLs",
            "Meta Robots Blocked URLs","Non-Canonical Pages","Missing Canonical Tags","Incorrect Canonical Tags",
            "Sitemap Missing Pages","Sitemap Not Crawled Pages","Hreflang Errors","Hreflang Conflicts",
            "Pagination Issues","Crawl Depth Distribution","Duplicate Parameter URLs"
        ],
        "D": [
            "Missing Title Tags","Duplicate Title Tags","Title Too Long","Title Too Short","Missing Meta Descriptions",
            "Duplicate Meta Descriptions","Meta Too Long","Meta Too Short","Missing H1","Multiple H1",
            "Duplicate Headings","Thin Content Pages","Duplicate Content Pages","Low Text-to-HTML Ratio",
            "Missing Image Alt Tags","Duplicate Alt Tags","Large Uncompressed Images","Pages Without Indexed Content",
            "Missing Structured Data","Structured Data Errors","Rich Snippet Warnings","Missing Open Graph Tags",
            "Long URLs","Uppercase URLs","Non-SEO-Friendly URLs","Too Many Internal Links",
            "Pages Without Incoming Links","Orphan Pages","Broken Anchor Links","Redirected Internal Links",
            "NoFollow Internal Links","Link Depth Issues","External Links Count","Broken External Links",
            "Anchor Text Issues"
        ],
        "E": [
            "Largest Contentful Paint (LCP)","First Contentful Paint (FCP)","Cumulative Layout Shift (CLS)",
            "Total Blocking Time","First Input Delay","Speed Index","Time to Interactive",
            "DOM Content Loaded","Total Page Size","Requests Per Page","Unminified CSS","Unminified JavaScript",
            "Render Blocking Resources","Excessive DOM Size","Third-Party Script Load","Server Response Time",
            "Image Optimization","Lazy Loading Issues","Browser Caching Issues","Missing GZIP / Brotli",
            "Resource Load Errors"
        ],
        "F": [
            "Mobile Friendly Test","Viewport Meta Tag","Small Font Issues","Tap Target Issues","Mobile Core Web Vitals",
            "Mobile Layout Issues","Intrusive Interstitials","Mobile Navigation Issues","HTTPS Implementation",
            "SSL Certificate Validity","Expired SSL","Mixed Content","Insecure Resources","Missing Security Headers",
            "Open Directory Listing","Login Pages Without HTTPS","Missing Hreflang","Incorrect Language Codes",
            "Hreflang Conflicts","Region Targeting Issues","Multi-Domain SEO Issues","Domain Authority",
            "Referring Domains","Total Backlinks","Toxic Backlinks","NoFollow Backlinks","Anchor Distribution",
            "Referring IPs","Lost / New Backlinks","JavaScript Rendering Issues","CSS Blocking",
            "Crawl Budget Waste","AMP Issues","PWA Issues","Canonical Conflicts","Subdomain Duplication",
            "Pagination Conflicts","Dynamic URL Issues","Lazy Load Conflicts","Sitemap Presence","Noindex Issues",
            "Structured Data Consistency","Redirect Correctness","Broken Rich Media","Social Metadata Presence",
            "Error Trend","Health Trend","Crawl Trend","Index Trend","Core Web Vitals Trend","Backlink Trend",
            "Keyword Trend","Historical Comparison","Overall Stability Index"
        ],
        "G": [
            "Competitor Health Score","Competitor Performance Comparison","Competitor Core Web Vitals Comparison",
            "Competitor SEO Issues Comparison","Competitor Broken Links Comparison","Competitor Authority Score",
            "Competitor Backlink Growth","Competitor Keyword Visibility","Competitor Rank Distribution",
            "Competitor Content Volume","Competitor Speed Comparison","Competitor Mobile Score",
            "Competitor Security Score","Competitive Gap Score","Competitive Opportunity Heatmap",
            "Competitive Risk Heatmap","Overall Competitive Rank"
        ],
        "H": [
            "Total Broken Links","Internal Broken Links","External Broken Links","Broken Links Trend",
            "Broken Pages by Impact","Status Code Distribution","Page Type Distribution","Fix Priority Score",
            "SEO Loss Impact","Affected Pages Count","Broken Media Links","Resolution Progress","Risk Severity Index"
        ],
        "I": [
            "High Impact Opportunities","Quick Wins Score","Long-Term Fixes","Traffic Growth Forecast",
            "Ranking Growth Forecast","Conversion Impact Score","Content Expansion Opportunities",
            "Internal Linking Opportunities","Speed Improvement Potential","Mobile Improvement Potential",
            "Security Improvement Potential","Structured Data Opportunities","Crawl Optimization Potential",
            "Backlink Opportunity Score","Competitive Gap ROI","Fix Roadmap Timeline","Time-to-Fix Estimate",
            "Cost-to-Fix Estimate","ROI Forecast","Overall Growth Readiness"
        ],
    }
    idx = 1
    for cat, names in sections.items():
        for name in names:
            METRIC_DESCRIPTORS[idx] = {"name": name, "category": cat}
            idx += 1

register_metrics()

def safe_request(url: str, timeout: int = 10) -> Tuple[int, bytes, float, Dict[str, str]]:
    t0 = time.time()
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "FFTechAuditBot/1.0"})
        latency = time.time() - t0
        return resp.status_code, resp.content or b"", latency, dict(resp.headers or {})
    except Exception:
        return 0, b"", time.time() - t0, {}

def is_valid_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except:
        return False

def grade_from_score(score: int) -> str:
    if score >= 95: return "A+"
    if score >= 90: return "A"
    if score >= 85: return "A-"
    if score >= 80: return "B+"
    if score >= 75: return "B"
    if score >= 70: return "B-"
    if score >= 65: return "C+"
    if score >= 60: return "C"
    if score >= 55: return "C-"
    if score >= 50: return "D+"
    return "D"

class AuditEngine:
    def __init__(self, url: str):
        if not is_valid_url(url):
            raise ValueError("Invalid URL")
        self.url = url
        self.domain = urlparse(url).netloc
        self.status_code, self.content, self.latency, self.headers = safe_request(url)
        self.html = self.content.decode(errors="ignore") if self.content else ""
        self.links_internal, self.links_external = [], []
        self.resources_css, self.resources_js, self.resources_img = [], [], []
        self._extract()

    def _extract(self):
        hrefs = re.findall(r'href=[\'"]?([^\'" >]+)', self.html, flags=re.IGNORECASE)
        srcs = re.findall(r'src=[\'"]?([^\'" >]+)', self.html, flags=re.IGNORECASE)
        for u in hrefs:
            full = urljoin(self.url, u)
            if urlparse(full).netloc == self.domain:
                self.links_internal.append(full)
            else:
                self.links_external.append(full)
        for s in srcs:
            full = urljoin(self.url, s)
            if full.lower().endswith(".css"): self.resources_css.append(full)
            elif full.lower().endswith(".js"): self.resources_js.append(full)
            elif any(full.lower().endswith(ext) for ext in(".png",".jpg",".jpeg",".webp",".gif",".svg")):
                self.resources_img.append(full)

    def compute_metrics(self) -> Dict[int, Dict[str, Any]]:
        m: Dict[int, Dict[str, Any]] = {}
        total_errors = total_warnings = total_notices = 0

        m[21] = {"value": 1 if 200 <= self.status_code < 300 else 0, "detail": f"Status {self.status_code}"}
        m[23] = {"value": 1 if 400 <= self.status_code < 500 else 0, "detail": f"Status {self.status_code}"}
        m[24] = {"value": 1 if 500 <= self.status_code < 600 else 0, "detail": f"Status {self.status_code}"}
        if m[23]["value"] or m[24]["value"]: total_errors += 1

        title_match = re.search(r"<title>(.*?)</title>", self.html, flags=re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""
        meta_desc_match = re.search(r'<meta[^>]+name=[\'"]description[\'"][^>]+content=\'"[\'"]', self.html, flags=re.IGNORECASE | re.DOTALL)
        meta_desc = meta_desc_match.group(1).strip() if meta_desc_match else ""
        m[41] = {"value": 1 if not title else 0, "detail": "Missing title"}
        m[43] = {"value": 1 if title and len(title) > 65 else 0, "detail": f"Title length {len(title) if title else 0}"}
        m[44] = {"value": 1 if title and len(title) < 15 else 0, "detail": f"Title length {len(title) if title else 0}"}
        m[45] = {"value": 1 if not meta_desc else 0, "detail": "Missing meta description"}
        m[47] = {"value": 1 if meta_desc and len(meta_desc) > 165 else 0, "detail": f"Meta length {len(meta_desc) if meta_desc else 0}"}
        m[48] = {"value": 1 if meta_desc and len(meta_desc) < 50 else 0, "detail": f"Meta length {len(meta_desc) if meta_desc else 0}"}
        total_errors += 1 if m[41]["value"] else 0
        total_warnings += (m[43]["value"] or m[44]["value"] or m[45]["value"])
        total_notices += (m[47]["value"] or m[48]["value"])

        h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", self.html, flags=re.IGNORECASE | re.DOTALL)
        m[49] = {"value": 1 if len(h1s) == 0 else 0, "detail": f"H1 count {len(h1s)}"}
        m[50] = {"value": 1 if len(h1s) > 1 else 0, "detail": f"H1 count {len(h1s)}"}
        total_warnings += (m[49]["value"] or m[50]["value"])

        img_tags = re.findall(r"<img[^>]*>", self.html, flags=re.IGNORECASE)
        missing_alts = sum(1 for tag in img_tags if re.search(r'alt=[\'"].*?[\'"]', tag, flags=re.IGNORECASE) is None)
        m[55] = {"value": missing_alts, "detail": f"Images missing alt: {missing_alts}"}
        total_notices += 1 if missing_alts > 0 else 0

        m[63] = {"value": 1 if len(self.url) > 115 else 0, "detail": f"URL length {len(self.url)}"}
        m[64] = {"value": 1 if re.search(r"[A-Z]", self.url) else 0, "detail": "Uppercase in URL" if re.search(r"[A-Z]", self.url) else "Lowercase"}

        is_https = self.url.startswith("https://")
        m[105] = {"value": 1 if is_https else 0, "detail": "HTTPS enabled" if is_https else "Not HTTPS"}
        total_errors += 0 if is_https else 1
        mixed = any(h.startswith("http://") for h in self.links_internal + self.resources_js + self.resources_css + self.resources_img) and is_https
        m[108] = {"value": 1 if mixed else 0, "detail": "Mixed content detected" if mixed else "No mixed content"}
        total_warnings += 1 if mixed else 0

        viewport_meta = re.search(r'<meta[^>]+name=[\'"]viewport[\'"]', self.html, flags=re.IGNORECASE)
        m[98] = {"value": 1 if bool(viewport_meta) else 0, "detail": "Viewport meta present" if viewport_meta else "Missing viewport"}
        total_warnings += 0 if viewport_meta else 1

        canonical = re.search(r'<link[^>]+rel=[\'"]canonical[\'"][^>]+href=\'"[\'"]', self.html, flags=re.IGNORECASE)
        m[32] = {"value": 0 if canonical else 1, "detail": f"Canonical present: {bool(canonical)}"}
        m[33] = {"value": "N/A", "detail": "Incorrect canonical needs multi-page check"}

        robots_url = f"{urlparse(self.url).scheme}://{self.domain}/robots.txt"
        rcode, rcontent, _, _ = safe_request(robots_url)
        m[29] = {"value": 0 if rcode == 200 and rcontent else 1, "detail": "robots.txt present" if rcode == 200 else "robots.txt missing"}
        sitemap_present = False
        for path in ["/sitemap.xml","/sitemap_index.xml","/sitemap"]:
            scode, scontent, _, _ = safe_request(f"{urlparse(self.url).scheme}://{self.domain}{path}")
            if scode == 200 and scontent:
                sitemap_present = True; break
        m[136] = {"value": 1 if sitemap_present else 0, "detail": "Sitemap present" if sitemap_present else "Sitemap missing"}

        page_size_kb = len(self.content)/1024 if self.content else 0
        m[84] = {"value": round(page_size_kb,2), "detail": f"Total page size KB {round(page_size_kb,2)}"}
        m[85] = {"value": len(self.resources_css)+len(self.resources_js)+len(self.resources_img), "detail": "Requests per page (approx)"}
        m[91] = {"value": round(self.latency*1000,2), "detail": f"Server response ms {round(self.latency*1000,2)}"}
        cache_control = (self.headers.get("Cache-Control") or "")
        m[94] = {"value": 0 if "max-age" in cache_control.lower() else 1, "detail": f"Cache-Control: {cache_control}"}
        content_encoding = (self.headers.get("Content-Encoding") or "").lower()
        compressed = any(enc in content_encoding for enc in ["gzip","br"])
        m[95] = {"value": 1 if compressed else 0, "detail": f"Content-Encoding: {content_encoding or 'none'}"}

        sec_required = ["Content-Security-Policy","Strict-Transport-Security","X-Frame-Options","X-Content-Type-Options","Referrer-Policy"]
        missing_sec = [h for h in sec_required if h not in self.headers]
        m[110] = {"value": len(missing_sec), "detail": f"Missing security headers: {missing_sec}"}

        broken_internal = 0
        for li in self.links_internal[:20]:
            code, _, _, _ = safe_request(li)
            if code >= 400 or code == 0: broken_internal += 1
        m[27] = {"value": broken_internal, "detail": "Broken internal links (sample)"}
        broken_external = 0
        for le in self.links_external[:20]:
            code, _, _, _ = safe_request(le)
            if code >= 400 or code == 0: broken_external += 1
        m[28] = {"value": broken_external, "detail": "Broken external links (sample)"}

        rb_css = len(self.resources_css)
        rb_js_sync = len(self.resources_js)
        m[88] = {"value": rb_css + rb_js_sync, "detail": f"Potential render-blocking (approx): {rb_css+rb_js_sync}"}
        dom_nodes = len(re.findall(r"<[a-zA-Z]+", self.html))
        m[89] = {"value": dom_nodes, "detail": f"Approx DOM nodes {dom_nodes}"}
        third_js = sum(1 for js in self.resources_js if urlparse(js).netloc != self.domain)
        m[90] = {"value": third_js, "detail": f"3rd-party scripts {third_js}"}
        large_imgs = sum(1 for img in self.resources_img if re.search(r"(large|hero|banner|@2x|\d{4}x\d{4})", img, flags=re.IGNORECASE))
        m[92] = {"value": large_imgs, "detail": "Potentially unoptimized images (heuristic)"}
        lazy_count = len(re.findall(r'loading=[\'"]lazy[\'"]', self.html, flags=re.IGNORECASE))
        m[93] = {"value": 0 if lazy_count>0 else 1, "detail": f"Lazy loading tags count {lazy_count}"}
        m[96] = {"value": "N/A", "detail": "Runtime resource errors need lab tools"}

        og_or_twitter = bool(re.search(r'property=[\'"]og:', self.html) or re.search(r'name=[\'"]twitter:', self.html))
        m[141] = {"value": 0 if og_or_twitter else 1, "detail": "Social metadata present" if og_or_twitter else "Missing social metadata"}
        m[62] = {"value": 0 if og_or_twitter else 1, "detail": "Open Graph/Twitter present" if og_or_twitter else "Missing"}

        m[168] = {"value": broken_internal + broken_external, "detail": "Total broken links (sample)"}
        m[169] = {"value": broken_internal, "detail": "Internal broken links"}
        m[170] = {"value": broken_external, "detail": "External broken links"}
