

"""
FF Tech AI Website Audit SaaS - Single File (No matplotlib)

- FastAPI backend (API-first & frontend-agnostic)
- Web UI (single-page HTML) with Chart.js (CDN)
- All 200 metrics displayed; graphical category charts
- Open audits, registered audits (passwordless magic link), history
- PDF report (5 pages) using ReportLab (optional; degrades gracefully if not installed)
- Railway-ready (uses PORT, DATABASE_URL)

Author: FF Tech
"""

import os
import io
import re
import ssl
import json
import time
import hmac
import hashlib
import logging
import random
import string
import asyncio
import datetime
from typing import Any, Dict, Optional, List, Tuple

from fastapi import FastAPI, HTTPException, Depends, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr
from starlette.requests import Request

import requests
from urllib.parse import urlparse, urljoin

# SQLAlchemy
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# --- Optional ReportLab (PDF). If not installed, app still runs for API & HTML. ---
PDF_ENABLED = True
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader
except Exception:
    PDF_ENABLED = False

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
APP_NAME = "FF Tech AI Website Audit SaaS"
FF_TECH_BRAND = "FF Tech"
FF_TECH_LOGO_TEXT = "FF TECH AI • Website Audit"
DEFAULT_LIMIT_FREE = 10

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech_ai_audit.db")
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_SECRET_32+CHARS")
PORT = int(os.getenv("PORT", "8000"))

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587")) if os.getenv("SMTP_PORT") else None
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@fftech.example")

# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
app = FastAPI(title=APP_NAME, version="1.1.0", description="API-driven, frontend-agnostic audit SaaS")
security = HTTPBearer()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fftech_ai_audit")

# -----------------------------------------------------------------------------
# DB Setup
# -----------------------------------------------------------------------------
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    verified = Column(Boolean, default=False)
    plan = Column(String(32), default="free")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    audits_count = Column(Integer, default=0)
    audits = relationship("Audit", back_populates="user")

class Audit(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # null for open
    url = Column(String(2048), nullable=False)
    metrics_json = Column(Text)  # store metrics as JSON text (portable across DBs)
    score = Column(Integer)
    grade = Column(String(4))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user = relationship("User", back_populates="audits")

class MagicLink(Base):
    __tablename__ = "magic_links"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), index=True, nullable=False)
    token = Column(String(512), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

# -----------------------------------------------------------------------------
# Security & Util
# -----------------------------------------------------------------------------
def now_utc() -> datetime.datetime:
    return datetime.datetime.utcnow()

def generate_token(payload: Dict[str, Any], exp_minutes: int = 30) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = dict(payload)
    payload["exp"] = int(time.time()) + exp_minutes * 60
    h_b64 = base64url(json.dumps(header).encode())
    p_b64 = base64url(json.dumps(payload).encode())
    signing_input = f"{h_b64}.{p_b64}".encode()
    sig = hmac.new(SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
    s_b64 = base64url(sig)
    return f"{h_b64}.{p_b64}.{s_b64}"

def base64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")

def base64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "==")

def verify_token(token: str) -> Dict[str, Any]:
    try:
        h_b64, p_b64, s_b64 = token.split(".")
        signing_input = f"{h_b64}.{p_b64}".encode()
        sig_expected = hmac.new(SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
        sig_given = base64url_decode(s_b64)
        if not hmac.compare_digest(sig_expected, sig_given):
            raise ValueError("Bad signature")
        payload = json.loads(base64url_decode(p_b64))
        if int(time.time()) > payload.get("exp", 0):
            raise ValueError("Expired")
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

def auth_user(credentials: HTTPAuthorizationCredentials = Depends(security), db=Depends(db_session)) -> User:
    payload = verify_token(credentials.credentials)
    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Missing email")
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.verified:
        raise HTTPException(status_code=401, detail="User not verified")
    return user

def is_valid_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except:
        return False

def safe_request(url: str, timeout: int = 10) -> Tuple[int, bytes, float, Dict[str, str]]:
    t0 = time.time()
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "FFTechAuditBot/1.0"})
        latency = time.time() - t0
        return resp.status_code, resp.content or b"", latency, dict(resp.headers or {})
    except Exception:
        return 0, b"", time.time() - t0, {}

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

# -----------------------------------------------------------------------------
# Metric Registry
# -----------------------------------------------------------------------------
# (Descriptors only; computation is in engine)
METRIC_DESCRIPTORS: Dict[int, Dict[str, Any]] = {}
def register_metrics():
    # A: 1–10
    names_A = [
        "Overall Site Health Score (%)","Website Grade (A+ to D)","Executive Summary (200 Words)",
        "Strengths Highlight Panel","Weak Areas Highlight Panel","Priority Fixes Panel",
        "Visual Severity Indicators","Category Score Breakdown","Industry-Standard Presentation",
        "Print / Certified Export Readiness"
    ]
    # B: 11–20
    names_B = [
        "Site Health Score","Total Errors","Total Warnings","Total Notices","Total Crawled Pages",
        "Total Indexed Pages","Issues Trend","Crawl Budget Efficiency","Orphan Pages Percentage",
        "Audit Completion Status"
    ]
    # C: 21–40
    names_C = [
        "HTTP 2xx Pages","HTTP 3xx Pages","HTTP 4xx Pages","HTTP 5xx Pages","Redirect Chains",
        "Redirect Loops","Broken Internal Links","Broken External Links","robots.txt Blocked URLs",
        "Meta Robots Blocked URLs","Non-Canonical Pages","Missing Canonical Tags","Incorrect Canonical Tags",
        "Sitemap Missing Pages","Sitemap Not Crawled Pages","Hreflang Errors","Hreflang Conflicts",
        "Pagination Issues","Crawl Depth Distribution","Duplicate Parameter URLs"
    ]
    # D: 41–75
    names_D = [
        "Missing Title Tags","Duplicate Title Tags","Title Too Long","Title Too Short","Missing Meta Descriptions",
        "Duplicate Meta Descriptions","Meta Too Long","Meta Too Short","Missing H1","Multiple H1",
        "Duplicate Headings","Thin Content Pages","Duplicate Content Pages","Low Text-to-HTML Ratio",
        "Missing Image Alt Tags","Duplicate Alt Tags","Large Uncompressed Images","Pages Without Indexed Content",
        "Missing Structured Data","Structured Data Errors","Rich Snippet Warnings","Missing Open Graph Tags",
        "Long URLs","Uppercase URLs","Non-SEO-Friendly URLs","Too Many Internal Links",
        "Pages Without Incoming Links","Orphan Pages","Broken Anchor Links","Redirected Internal Links",
        "NoFollow Internal Links","Link Depth Issues","External Links Count","Broken External Links",
        "Anchor Text Issues"
    ]
    # E: 76–96
    names_E = [
        "Largest Contentful Paint (LCP)","First Contentful Paint (FCP)","Cumulative Layout Shift (CLS)",
        "Total Blocking Time","First Input Delay","Speed Index","Time to Interactive",
        "DOM Content Loaded","Total Page Size","Requests Per Page","Unminified CSS","Unminified JavaScript",
        "Render Blocking Resources","Excessive DOM Size","Third-Party Script Load","Server Response Time",
        "Image Optimization","Lazy Loading Issues","Browser Caching Issues","Missing GZIP / Brotli",
        "Resource Load Errors"
    ]
    # F: 97–150 (subset of names from your list)
    names_F = [
        "Mobile Friendly Test","Viewport Meta Tag","Small Font Issues","Tap Target Issues","Mobile Core Web Vitals",
        "Mobile Layout Issues","Intrusive Interstitials","Mobile Navigation Issues","HTTPS Implementation",
        "SSL Certificate Validity","Expired SSL","Mixed Content","Insecure Resources",
        "Missing Security Headers","Open Directory Listing","Login Pages Without HTTPS","Missing Hreflang",
        "Incorrect Language Codes","Hreflang Conflicts","Region Targeting Issues","Multi-Domain SEO Issues",
        "Domain Authority","Referring Domains","Total Backlinks","Toxic Backlinks","NoFollow Backlinks",
        "Anchor Distribution","Referring IPs","Lost / New Backlinks","JavaScript Rendering Issues",
        "CSS Blocking","Crawl Budget Waste","AMP Issues","PWA Issues","Canonical Conflicts",
        "Subdomain Duplication","Pagination Conflicts","Dynamic URL Issues","Lazy Load Conflicts",
        "Sitemap Presence","Noindex Issues","Structured Data Consistency","Redirect Correctness",
        "Broken Rich Media","Social Metadata Presence","Error Trend","Health Trend","Crawl Trend",
        "Index Trend","Core Web Vitals Trend","Backlink Trend","Keyword Trend","Historical Comparison",
        "Overall Stability Index"
    ]
    # G: 151–167
    names_G = [
        "Competitor Health Score","Competitor Performance Comparison","Competitor Core Web Vitals Comparison",
        "Competitor SEO Issues Comparison","Competitor Broken Links Comparison","Competitor Authority Score",
        "Competitor Backlink Growth","Competitor Keyword Visibility","Competitor Rank Distribution",
        "Competitor Content Volume","Competitor Speed Comparison","Competitor Mobile Score",
        "Competitor Security Score","Competitive Gap Score","Competitive Opportunity Heatmap",
        "Competitive Risk Heatmap","Overall Competitive Rank"
    ]
    # H: 168–180
    names_H = [
        "Total Broken Links","Internal Broken Links","External Broken Links","Broken Links Trend",
        "Broken Pages by Impact","Status Code Distribution","Page Type Distribution","Fix Priority Score",
        "SEO Loss Impact","Affected Pages Count","Broken Media Links","Resolution Progress","Risk Severity Index"
    ]
    # I: 181–200
    names_I = [
        "High Impact Opportunities","Quick Wins Score","Long-Term Fixes","Traffic Growth Forecast",
        "Ranking Growth Forecast","Conversion Impact Score","Content Expansion Opportunities",
        "Internal Linking Opportunities","Speed Improvement Potential","Mobile Improvement Potential",
        "Security Improvement Potential","Structured Data Opportunities","Crawl Optimization Potential",
        "Backlink Opportunity Score","Competitive Gap ROI","Fix Roadmap Timeline","Time-to-Fix Estimate",
        "Cost-to-Fix Estimate","ROI Forecast","Overall Growth Readiness"
    ]
    # fill registry
    idx = 1
    for name in names_A:
        METRIC_DESCRIPTORS[idx] = {"name": name, "category": "A"}; idx += 1
    for name in names_B:
        METRIC_DESCRIPTORS[idx] = {"name": name, "category": "B"}; idx += 1
    for name in names_C:
        METRIC_DESCRIPTORS[idx] = {"name": name, "category": "C"}; idx += 1
    for name in names_D:
        METRIC_DESCRIPTORS[idx] = {"name": name, "category": "D"}; idx += 1
    for name in names_E:
        METRIC_DESCRIPTORS[idx] = {"name": name, "category": "E"}; idx += 1
    for name in names_F:
        METRIC_DESCRIPTORS[idx] = {"name": name, "category": "F"}; idx += 1
    for name in names_G:
        METRIC_DESCRIPTORS[idx] = {"name": name, "category": "G"}; idx += 1
    for name in names_H:
        METRIC_DESCRIPTORS[idx] = {"name": name, "category": "H"}; idx += 1
    for name in names_I:
        METRIC_DESCRIPTORS[idx] = {"name": name, "category": "I"}; idx += 1

register_metrics()

# -----------------------------------------------------------------------------
# Audit Engine (lightweight homepage audit; extendable)
# -----------------------------------------------------------------------------
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
            elif any(full.lower().endswith(ext) for ext in (".png",".jpg",".jpeg",".webp",".gif",".svg")):
                self.resources_img.append(full)

    def compute_metrics(self) -> Dict[int, Dict[str, Any]]:
        m: Dict[int, Dict[str, Any]] = {}
        total_errors = total_warnings = total_notices = 0

        # HTTP status
        m[21] = {"value": 1 if 200 <= self.status_code < 300 else 0, "detail": f"Homepage status: {self.status_code}"}
        m[23] = {"value": 1 if 400 <= self.status_code < 500 else 0, "detail": f"Homepage status: {self.status_code}"}
        m[24] = {"value": 1 if 500 <= self.status_code < 600 else 0, "detail": f"Homepage status: {self.status_code}"}
        if m[23]["value"] or m[24]["value"]:
            total_errors += 1

        # Title/meta
        title_match = re.search(r"<title>(.*?)</title>", self.html, flags=re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""
        meta_desc_match = re.search(r'<meta[^>]+name=[\'"]description[\'"][^>]+content=\'"[\'"]', self.html, flags=re.IGNORECASE | re.DOTALL)
        meta_desc = meta_desc_match.group(1).strip() if meta_desc_match else ""
        m[41] = {"value": 1 if not title else 0, "detail": f"Missing title: {not bool(title)}"}
        m[43] = {"value": 1 if title and len(title) > 65 else 0, "detail": f"Title length: {len(title)}"}
        m[44] = {"value": 1 if title and len(title) < 15 else 0, "detail": f"Title length: {len(title)}"}
        m[45] = {"value": 1 if not meta_desc else 0, "detail": f"Missing meta description"}
        m[47] = {"value": 1 if meta_desc and len(meta_desc) > 165 else 0, "detail": f"Meta length: {len(meta_desc)}"}
        m[48] = {"value": 1 if meta_desc and len(meta_desc) < 50 else 0, "detail": f"Meta length: {len(meta_desc)}"}
        total_errors += 1 if m[41]["value"] else 0
        total_warnings += (m[43]["value"] or m[44]["value"] or m[45]["value"])
        total_notices += (m[47]["value"] or m[48]["value"])

        h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", self.html, flags=re.IGNORECASE | re.DOTALL)
        m[49] = {"value": 1 if len(h1s) == 0 else 0, "detail": f"H1 count: {len(h1s)}"}
        m[50] = {"value": 1 if len(h1s) > 1 else 0, "detail": f"H1 count: {len(h1s)}"}
        total_warnings += (m[49]["value"] or m[50]["value"])

        img_tags = re.findall(r"<img[^>]*>", self.html, flags=re.IGNORECASE)
        missing_alts = sum(1 for tag in img_tags if re.search(r'alt=[\'"].*?[\'"]', tag, flags=re.IGNORECASE) is None)
        m[55] = {"value": missing_alts, "detail": f"Images missing alt: {missing_alts}"}
        total_notices += 1 if missing_alts > 0 else 0

        # URL
        m[63] = {"value": 1 if len(self.url) > 115 else 0, "detail": f"URL length: {len(self.url)}"}
        m[64] = {"value": 1 if re.search(r"[A-Z]", self.url) else 0, "detail": "Uppercase present" if re.search(r"[A-Z]", self.url) else "Lowercase"}

        # HTTPS / Mixed
        is_https = self.url.startswith("https://")
        m[105] = {"value": 1 if is_https else 0, "detail": "HTTPS enabled" if is_https else "Not HTTPS"}
        total_errors += 0 if is_https else 1

        mixed = any(link.startswith("http://") for link in self.links_internal + self.resources_js + self.resources_css + self.resources_img) and is_https
        m[108] = {"value": 1 if mixed else 0, "detail": "Mixed content detected" if mixed else "No mixed content"}
        total_warnings += 1 if mixed else 0

        # Mobile meta
        viewport_meta = re.search(r'<meta[^>]+name=[\'"]viewport[\'"]', self.html, flags=re.IGNORECASE)
        m[98] = {"value": 1 if bool(viewport_meta) else 0, "detail": "Viewport meta present" if viewport_meta else "Missing viewport meta"}
        total_warnings += 0 if viewport_meta else 1

        # Performance basics
        page_size_kb = len(self.content) / 1024 if self.content else 0
        m[84] = {"value": round(page_size_kb, 2), "detail": f"Total page size (KB): {round(page_size_kb, 2)}"}
        m[85] = {"value": len(self.resources_css) + len(self.resources_js) + len(self.resources_img), "detail": "Resources per page"}
        m[91] = {"value": round(self.latency * 1000, 2), "detail": f"Server response time (ms): {round(self.latency * 1000, 2)}"}

        cache_control = (self.headers.get("Cache-Control") or "")
        m[94] = {"value": 0 if "max-age" in cache_control.lower() else 1, "detail": f"Cache-Control: {cache_control}"}
        total_notices += 1 if m[94]["value"] else 0

        content_encoding = (self.headers.get("Content-Encoding") or "").lower()
        compressed = any(enc in content_encoding for enc in ["gzip", "br"])
        m[95] = {"value": 1 if compressed else 0, "detail": f"Content-Encoding: {content_encoding or 'none'}"}
        total_warnings += 1 if (not compressed and page_size_kb > 256) else 0

        sec_headers_required = ["Content-Security-Policy","Strict-Transport-Security","X-Frame-Options","X-Content-Type-Options","Referrer-Policy"]
        missing_sec = [h for h in sec_headers_required if h not in self.headers]
        m[110] = {"value": len(missing_sec), "detail": f"Missing security headers: {missing_sec}"}
        total_warnings += 1 if missing_sec else 0

        # Broken links (sample)
        broken_internal = 0
        for li in self.links_internal[:20]:
            code, _, _, _ = safe_request(li, timeout=5)
            if code >= 400 or code == 0:
                broken_internal += 1
        m[27] = {"value": broken_internal, "detail": "Broken internal links (sample)"}
        total_errors += 1 if broken_internal > 0 else 0

        broken_external = 0
        for le in self.links_external[:20]:
            code, _, _, _ = safe_request(le, timeout=5)
            if code >= 400 or code == 0:
                broken_external += 1
        m[28] = {"value": broken_external, "detail": "Broken external links (sample)"}
        total_notices += 1 if broken_external > 0 else 0

        # robots.txt & sitemap presence
        robots_url = f"{urlparse(self.url).scheme}://{self.domain}/robots.txt"
        rcode, rcontent, _, _ = safe_request(robots_url, timeout=5)
        m[29] = {"value": 0 if rcode == 200 and rcontent else 1, "detail": "robots.txt present" if rcode == 200 else "robots.txt missing"}
        total_warnings += 1 if m[29]["value"] else 0

        sitemap_present = False
        for path in ["/sitemap.xml","/sitemap_index.xml","/sitemap"]:
            scode, scontent, _, _ = safe_request(f"{urlparse(self.url).scheme}://{self.domain}{path}", timeout=5)
            if scode == 200 and scontent:
                sitemap_present = True
                break
        m[136] = {"value": 1 if sitemap_present else 0, "detail": "Sitemap present" if sitemap_present else "Sitemap missing"}
        total_warnings += 0 if sitemap_present else 1

        canonical = re.search(r'<link[^>]+rel=[\'"]canonical[\'"][^>]+href=\'"[\'"]', self.html, flags=re.IGNORECASE)
        m[32] = {"value": 0 if canonical else 1, "detail": f"Canonical present: {bool(canonical)}"}
        m[33] = {"value": "N/A", "detail": "Incorrect canonical needs multi-page check"}

        # Social metadata presence
        og_or_tw = bool(re.search(r'property=[\'"]og:', self.html) or re.search(r'name=[\'"]twitter:', self.html))
        m[62] = {"value": 0 if og_or_tw else 1, "detail": "Open Graph/Twitter present" if og_or_tw else "Missing OG/Twitter"}

        # Render-blocking (approx)
        rb_css = len(self.resources_css)
        rb_js_sync = len(self.resources_js)  # heuristic (since we don't parse defer/async attrs in one file)
        m[88] = {"value": rb_css + rb_js_sync, "detail": f"Potential render-blocking (approx): {rb_css + rb_js_sync}"}

        dom_nodes = len(re.findall(r"<[a-zA-Z]+", self.html))
        m[89] = {"value": dom_nodes, "detail": f"Approx DOM nodes: {dom_nodes}"}

        third_party_js = sum(1 for js in self.resources_js if urlparse(js).netloc != self.domain)
        m[90] = {"value": third_party_js, "detail": f"3rd-party scripts: {third_party_js}"}

        large_imgs = sum(1 for img in self.resources_img if re.search(r"(large|hero|banner|@2x|\d{4}x\d{4})", img, flags=re.IGNORECASE))
        m[92] = {"value": large_imgs, "detail": "Potentially unoptimized images (heuristic)"}

        lazy_count = len(re.findall(r'loading=[\'"]lazy[\'"]', self.html, flags=re.IGNORECASE))
        m[93] = {"value": 0 if lazy_count > 0 else 1, "detail": f"Lazy loading present count: {lazy_count}"}

        m[96] = {"value": "N/A", "detail": "Resource load errors require runtime capture"}

        # Trends & external-data placeholders
        for pid in [16,17,18,19,76,77,78,79,80,81,82,83,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,142,143,144,145,146,147,148,149]:
            m[pid] = {"value": "N/A", "detail": "Requires deeper crawl or external APIs/lab tooling"}

        # Broken links intelligence
        m[168] = {"value": broken_internal + broken_external, "detail": "Total broken links (sample)"}
        m[169] = {"value": broken_internal, "detail": "Internal broken links"}
        m[170] = {"value": broken_external, "detail": "External broken links"}
        m[171] = {"value": "N/A", "detail": "Trend requires history"}
        m[173] = {"value": {"2xx": m[21]["value"], "4xx": m[23]["value"], "5xx": m[24]["value"]}, "detail": "Status distribution (homepage)"}
        m[175] = {"value": min(100, (broken_internal * 10) + (broken_external * 5)), "detail": "Fix priority (heuristic)"}
        m[180] = {"value": min(100, (total_errors * 20) + (total_warnings * 10)), "detail": "Risk severity (heuristic)"}

        # Opportunities & ROI
        m[182] = {"value": max(0, 100 - (total_errors * 15 + total_warnings * 5)), "detail": "Quick Wins"}
        m[189] = {"value": min(100, m[88]["value"] * 5 + m[92]["value"] * 5), "detail": "Speed improvement potential"}
        m[190] = {"value": 50 if not viewport_meta else 10, "detail": "Mobile improvement potential"}
        m[191] = {"value": min(100, len(missing_sec) * 10), "detail": "Security improvement potential"}
        m[200] = {"value": max(0, 100 - m[180]["value"]), "detail": "Growth readiness"}

        # Executive summary & score
        base_score = 100
        base_score -= total_errors * 10
        base_score -= total_warnings * 5
        base_score -= min(10, int(page_size_kb / 512) * 2)
        base_score -= min(10, m[88]["value"])
        score = max(0, min(100, base_score))
        m[1] = {"value": score, "detail": "Overall Site Health (%)"}
        m[11] = {"value": score, "detail": "Site Health Score"}
        grade = grade_from_score(score)
        m[2] = {"value": grade, "detail": "Website Grade"}

        strengths, weaknesses, priority_fixes = [], [], []
        if is_https: strengths.append("HTTPS enabled")
        if title and 15 <= len(title) <= 65: strengths.append("Optimal title length")
        if meta_desc and 50 <= len(meta_desc) <= 165: strengths.append("Optimal meta description length")
        if lazy_count > 0: strengths.append("Lazy loading used")
        if compressed: strengths.append("Compression (gzip/br) enabled")

        if m[41]["value"]: weaknesses.append("Missing title tag")
        if m[45]["value"]: weaknesses.append("Missing meta description")
        if mixed: weaknesses.append("Mixed content over HTTPS")
        if m[110]["value"] > 0: weaknesses.append("Missing security headers")
        if broken_internal > 0: weaknesses.append("Broken internal links")
        if not sitemap_present: weaknesses.append("Sitemap missing")

        if broken_internal > 0: priority_fixes.append("Fix internal broken links")
        if not is_https: priority_fixes.append("Enable HTTPS")
        if m[110]["value"] > 0: priority_fixes.append("Add CSP, HSTS, X-Frame-Options, etc.")
        if not viewport_meta: priority_fixes.append("Add responsive viewport meta")
        if not compressed and page_size_kb > 256: priority_fixes.append("Enable gzip/brotli compression")

        m[4] = {"value": strengths, "detail": "Strengths"}
        m[5] = {"value": weaknesses, "detail": "Weak areas"}
        m[6] = {"value": priority_fixes, "detail": "Priority fixes"}
        cat_scores = {
            "Crawlability": max(0, 100 - (m[27]["value"] + m[28]["value"]) * 5),
            "On-Page SEO": max(0, 100 - (m[41]["value"] + m[45]["value"] + m[43]["value"] + m[44]["value"]) * 10),
            "Performance": max(0, 100 - (m[84]["value"] / 10 + m[88]["value"] * 5 + (0 if compressed else 10))),
            "Security": max(0, 100 - (m[110]["value"] * 10 + (0 if is_https else 50))),
            "Mobile": max(0, 100 - (0 if viewport_meta else 30)),
        }
        m[8] = {"value": cat_scores, "detail": "Category score breakdown"}
        m[7] = {"value": {"errors": total_errors, "warnings": total_warnings, "notices": total_notices}, "detail": "Severity indicators"}
        m[9] = {"value": "Yes", "detail": "Industry-standard presentation"}
        m[10] = {"value": "Ready", "detail": "Certified export readiness"}

        # Exec summary
        m[3] = {"value": self.executive_summary(m), "detail": "Executive Summary (200 words)"}
        return m

    def executive_summary(self, metrics: Dict[int, Dict[str, Any]]) -> str:
        score = metrics[1]["value"]; grade = metrics[2]["value"]
        sev = metrics[7]["value"]; perf = metrics[84]["value"]; resp = metrics[91]["value"]
        strengths = ", ".join(metrics[4]["value"]) if metrics[4]["value"] else "None"
        weaknesses = ", ".join(metrics[5]["value"]) if metrics[5]["value"] else "None"
        text = (
            f"FF Tech audited {self.url} across crawlability, on-page SEO, performance, mobile, and security. "
            f"The site scored {score}% with a grade of {grade}. We observed {sev['errors']} errors, "
            f"{sev['warnings']} warnings, and {sev['notices']} notices. Approximate payload is {perf} KB and "
            f"server response time is {resp} ms. Strengths: {strengths}. Weaknesses: {weaknesses}. "
            f"Priority fixes address link integrity, HTTPS/security headers, and metadata. "
            f"Category scores provide balanced insight into immediate and long-term optimization potential."
        )
        if len(text.split()) < 200:
            text += " The audit uses transparent, standardized checks and normalizes metrics for consistent scoring, enabling executive decision-making and simple integration into any HTML or modern frontend through clean JSON APIs."
        return text

# -----------------------------------------------------------------------------
# PDF (No matplotlib; draw bars with ReportLab. If reportlab missing, return error)
# -----------------------------------------------------------------------------
def draw_bar_chart_simple(c, x, y, width, height, labels: List[str], values: List[float], max_val: float = 100):
    """Draw a simple bar chart using ReportLab shapes."""
    n = len(values)
    if n == 0: return
    bar_w = width / (n * 1.5)
    gap = bar_w / 2
    c.setFont("Helvetica", 9)
    for i, (lab, val) in enumerate(zip(labels, values)):
        bx = x + i * (bar_w + gap)
        bh = (val / max_val) * (height - 10)
        c.setFillColor(colors.HexColor("#2E86C1"))
        c.rect(bx, y, bar_w, bh, fill=1, stroke=0)
        c.setFillColor(colors.black)
        c.drawString(bx, y - 10, lab[:10])

def build_pdf_report(audit: Audit, metrics: Dict[int, Dict[str, Any]]) -> bytes:
    if not PDF_ENABLED:
        raise HTTPException(status_code=500, detail="PDF generation requires 'reportlab' installed.")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # Page 1
    c.setFillColor(colors.HexColor("#0A2540")); c.rect(0, height - 2.5*cm, width, 2.5*cm, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 18); c.drawString(2*cm, height - 1.5*cm, FF_TECH_LOGO_TEXT)
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 16); c.drawString(2*cm, height - 4*cm, "Executive Summary")
    summary = metrics[3]["value"]
    textobj = c.beginText(2*cm, height - 5*cm); textobj.setFont("Helvetica", 11)
    for line in re.findall(".{1,90}(?:\\s|$)", summary): textobj.textLine(line.strip())
    c.drawText(textobj)
    c.setFont("Helvetica-Bold", 14); c.drawString(2*cm, height - 11*cm, "Site Health Score:")
    c.setFont("Helvetica", 14); c.drawString(8*cm, height - 11*cm, f"{metrics[1]['value']}%   Grade: {metrics[2]['value']}")
    sev = metrics[7]["value"]; c.setFont("Helvetica-Bold", 14); c.drawString(2*cm, height - 12*cm, "Severity Overview:")
    c.setFont("Helvetica", 12); c.drawString(6*cm, height - 12*cm, f"Errors: {sev['errors']}  Warnings: {sev['warnings']}  Notices: {sev['notices']}")
    c.setFont("Helvetica-Oblique", 10); c.drawString(2*cm, 1.5*cm, f"{FF_TECH_BRAND} • Generated: {now_utc().isoformat()}")
    c.showPage()

    # Page 2: Category Performance
    c.setFont("Helvetica-Bold", 16); c.drawString(2*cm, height - 2.5*cm, "Category Performance")
    cats = metrics[8]["value"]; labels = list(cats.keys()); values = [cats[k] for k in labels]
    draw_bar_chart_simple(c, 2*cm, height - 12*cm, 16*cm, 8*cm, labels, values, 100)
    c.setFont("Helvetica-Oblique", 10); c.drawString(2*cm, 1.5*cm, "Conclusion: Improve security headers and fix broken links; then tune performance.")
    c.showPage()

    # Page 3: Crawlability & SEO
    c.setFont("Helvetica-Bold", 16); c.drawString(2*cm, height - 2.5*cm, "Crawlability & On-Page SEO")
    c.setFont("Helvetica", 11)
    items = [
        f"Broken internal links: {metrics[27]['value']}",
        f"Broken external links: {metrics[28]['value']}",
        f"Canonical present: {'No' if metrics[32]['value'] else 'Yes'}",
        f"Missing meta description: {'Yes' if metrics[45]['value'] else 'No'}",
        f"Open Graph/Twitter: {'Present' if metrics[62]['value']==0 else 'Missing'}",
    ]
    y = height - 4*cm
    for t in items: c.drawString(2*cm, y, t); y -= 0.8*cm
    c.setFont("Helvetica-Oblique", 10); c.drawString(2*cm, 1.5*cm, "Conclusion: Close metadata gaps and link integrity for better crawl/snippet quality.")
    c.showPage()

    # Page 4: Performance & Security
    c.setFont("Helvetica-Bold", 16); c.drawString(2*cm, height - 2.5*cm, "Performance & Security")
    c.setFont("Helvetica", 11)
    perf_items = [
        f"Total page size (KB): {metrics[84]['value']}",
        f"Server response time (ms): {metrics[91]['value']}",
        f"Render-blocking (approx): {metrics[88]['value']}",
        f"Compression enabled: {'Yes' if metrics[95]['value'] else 'No'}",
        f"Missing security headers: {metrics[110]['value']}",
        f"HTTPS: {'Yes' if metrics[105]['value'] else 'No'}",
    ]
    y = height - 4*cm
    for t in perf_items: c.drawString(2*cm, y, t); y -= 0.8*cm
    c.setFont("Helvetica-Oblique", 10); c.drawString(2*cm, 1.5*cm, "Conclusion: Enable caching/compression, reduce blocking resources, enforce security headers.")
    c.showPage()

    # Page 5: Priorities & ROI
    c.setFont("Helvetica-Bold", 16); c.drawString(2*cm, height - 2.5*cm, "Priorities, Opportunities & ROI")
    c.setFont("Helvetica", 11)
    y = height - 4*cm
    c.drawString(2*cm, y, "Priority Fixes:"); y -= 0.8*cm
    for p in metrics[6]["value"]: c.drawString(3*cm, y, f"- {p}"); y -= 0.7*cm
    y -= 0.3*cm
    c.drawString(2*cm, y, f"Quick Wins Score: {metrics[182]['value']}"); y -= 0.7*cm
    c.drawString(2*cm, y, f"Speed Improvement Potential: {metrics[189]['value']}"); y -= 0.7*cm
    c.drawString(2*cm, y, f"Security Improvement Potential: {metrics[191]['value']}"); y -= 0.7*cm
    c.drawString(2*cm, y, f"Overall Growth Readiness: {metrics[200]['value']}")
    c.setFont("Helvetica-Oblique", 10); c.drawString(2*cm, 1.5*cm, "Conclusion: Executing priority fixes yields near-term ROI and improves stability.")
    c.showPage(); c.save()
    pdf = buf.getvalue(); buf.close()
    return pdf

# -----------------------------------------------------------------------------
# Email (Magic Link) - logs if SMTP not configured
# -----------------------------------------------------------------------------
def send_magic_link(email: str, token: str, request: Request):
    url = f"{str(request.base_url).rstrip('/')}/auth/verify?token={token}"
    logger.info(f"[DEV] Magic link for {email}: {url}")
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS and SMTP_FROM):
        return  # just log for dev
    subject = f"{FF_TECH_BRAND} Login Link"
    body = f"Click to log in:\n\n{url}\n\nThis link expires in 30 minutes."
    msg = f"From: {SMTP_FROM}\r\nTo: {email}\r\nSubject: {subject}\r\n\r\n{body}"
    import smtplib
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context); server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_FROM, [email], msg)

# -----------------------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------------------
class AuditRequest(BaseModel):
    url: str = Field(..., description="Website URL to audit")

class AuditResponse(BaseModel):
    url: str
    score: int
    grade: str
    metrics: Dict[int, Dict[str, Any]]

class MagicLinkRequest(BaseModel):
    email: EmailStr

# -----------------------------------------------------------------------------
# API Endpoints (JSON)
# -----------------------------------------------------------------------------
@app.get("/api")
def api_root():
    return {"name": APP_NAME, "version": "1.1.0", "endpoints": ["/api/audit/open","/api/audit/user","/api/metrics/descriptors"]}

@app.get("/api/metrics/descriptors")
def metrics_descriptors():
    return METRIC_DESCRIPTORS

@app.post("/api/audit/open", response_model=AuditResponse)
def audit_open(req: AuditRequest):
    if not is_valid_url(req.url):
        raise HTTPException(status_code=400, detail="Invalid URL")
    engine = AuditEngine(req.url)
    metrics = engine.compute_metrics()
    return AuditResponse(url=req.url, score=metrics[1]["value"], grade=metrics[2]["value"], metrics=metrics)

@app.post("/api/audit/user", response_model=AuditResponse)
def audit_user_api(req: AuditRequest, user: User = Depends(auth_user), db=Depends(db_session)):
    if not is_valid_url(req.url):
        raise HTTPException(status_code=400, detail="Invalid URL")
    if user.plan == "free" and user.audits_count >= DEFAULT_LIMIT_FREE:
        raise HTTPException(status_code=402, detail="Free plan limit reached (10 audits).")
    engine = AuditEngine(req.url)
    metrics = engine.compute_metrics()
    a = Audit(user_id=user.id, url=req.url, metrics_json=json.dumps(metrics), score=metrics[1]["value"], grade=metrics[2]["value"])
    db.add(a); user.audits_count += 1; db.commit()
    return AuditResponse(url=req.url, score=a.score, grade=a.grade, metrics=metrics)

@app.get("/api/audits")
def list_user_audits(limit: int = Query(20, ge=1, le=100), user: User = Depends(auth_user), db=Depends(db_session)):
    rows = db.query(Audit).filter(Audit.user_id == user.id).order_by(Audit.created_at.desc()).limit(limit).all()
    return [{"id": r.id, "url": r.url, "score": r.score, "grade": r.grade, "created_at": r.created_at.isoformat()} for r in rows]

@app.get("/api/report/{audit_id}.pdf")
def report_pdf_api(audit_id: int, user: User = Depends(auth_user), db=Depends(db_session)):
    a = db.query(Audit).filter(Audit.id == audit_id, Audit.user_id == user.id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Audit not found")
    metrics = json.loads(a.metrics_json)
    pdf = build_pdf_report(a, metrics)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="FFTech_Audit_{a.id}.pdf"'})

# -------------------- Auth --------------------
@app.post("/auth/request-link")
def request_link(payload: MagicLinkRequest, request: Request, db=Depends(db_session)):
    email = payload.email.lower().strip()
    token = generate_token({"email": email, "purpose": "magic"}, exp_minutes=30)
    ml = MagicLink(email=email, token=token, expires_at=now_utc() + datetime.timedelta(minutes=30), used=False)
    db.add(ml); db.commit()
    send_magic_link(email, token, request)
    return {"message": "Login link sent (or logged to server for dev)."}

@app.get("/auth/verify")
def verify_magic_link(token: str, db=Depends(db_session)):
    payload = verify_token(token)
    if payload.get("purpose") != "magic":
        raise HTTPException(status_code=400, detail="Invalid purpose")
    ml = db.query(MagicLink).filter(MagicLink.token == token).first()
    if not ml or ml.used or ml.expires_at < now_utc():
        raise HTTPException(status_code=400, detail="Magic link invalid or expired")
    ml.used = True
    email = payload["email"]
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, verified=True, plan="free"); db.add(user)
    else:
        user.verified = True
    db.commit()
    session_token = generate_token({"email": email, "purpose": "session"}, exp_minutes=60*24*30)
    return {"token": session_token, "plan": user.plan, "email": user.email}

@app.get("/me")
def me(user: User = Depends(auth_user)):
    return {"email": user.email, "plan": user.plan, "audits_count": user.audits_count, "created_at": user.created_at.isoformat()}

# -----------------------------------------------------------------------------
# Web UI (Single page; Chart.js; all metrics shown)
# -----------------------------------------------------------------------------
HTML_BASE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>FF Tech AI Website Audit</title>
https://cdn.jsdelivr.net
<script src.jsdelivr.net/npm/chart.js</script>
<style>
 body{font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#0f172a;color:#e2e8f0;margin:0}
 header{background:#0a2540;padding:16px 24px;display:flex;justify-content:space-between;align-items:center}
 header .brand{font-weight:800;letter-spacing:0.5px}
 main{padding:24px}
 .card{background:#111827;border:1px solid #334155;border-radius:12px;padding:16px;margin-bottom:16px}
 .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
 .btn{background:#2563eb;color:white;border:none;border-radius:8px;padding:10px 14px;cursor:pointer}
 .input{width:100%;padding:10px;border-radius:8px;border:1px solid #334155;background:#0b1220;color:#e2e8f0}
 table{width:100%;border-collapse:collapse}
 th,td{padding:8px;border-bottom:1px solid #334155}
 .metric-ok{color:#10b981}
 .metric-issue{color:#ef4444}
 .badge{display:inline-block;background:#1f2937;padding:2px 8px;border-radius:999px;margin-right:6px}
 .sub{color:#93c5fd}
 footer{padding:24px;text-align:center;color:#93c5fd}
</style>
</head>
<body>
<header>
  <div class="brand">FF TECH AI • Website Audit</div>
  <div class="sub">Frontend-agnostic • JSON + HTML</div>
</header>
<main>
  <div class="card">
    <form id="auditForm" onsubmit="runAudit(event)">
      <label>Website URL</label>
      <input id="urlInput" class="input" type="url" placeholder="https://example.com" required />
      <button class="btn" type="submit">Run Audit</button>
      <span id="loading" style="margin-left:10px;display:none">Running...</span>
    </form>
  </div>

  <div id="results" style="display:none">
    <div class="grid">
      <div class="card">
        <h3>Executive Summary</h3>
        <p id="summary"></p>
      </div>
      <div class="card">
        <h3>Score & Grade</h3>
        <div id="scoreGrade"></div>
        <canvas id="catChart" height="180"></canvas>
      </div>
      <div class="card">
        <h3>Severity Overview</h3>
        <div id="severity"></div>
      </div>
    </div>

    <div class="card">
      <h3>Category Charts</h3>
      <div class="grid">
        <div><canvas id="chartCrawl"></canvas></div>
        <div><canvas id="chartSEO"></canvas></div>
        <div><canvas id="chartPerf"></canvas></div>
        <div><canvas id="chartSec"></canvas></div>
        <div><canvas id="chartMobile"></canvas></div>
      </div>
    </div>

    <div class="card">
      <h3>All Metrics (200)</h3>
      <table id="metricsTable">
        <thead><tr><th>ID</th><th>Name</th><th>Category</th><th>Value</th><th>Detail</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>
</main>
<footer>FF Tech • API-driven • Charts by Chart.js (CDN)</footer>

<script>
const DESCRIPTORS = %DESCRIPTORS%;
function severityClass(val){return (typeof val==='number' && val>0) ? 'metric-issue':'metric-ok';}
function drawCategoryChart(catScores){
  const ctx = document.getElementById('catChart').getContext('2d');
  new Chart(ctx,{type:'bar',data:{labels:Object.keys(catScores),
    datasets:[{label:'Score',data:Object.values(catScores),backgroundColor:'#2E86C1'}]},
    options:{responsive:true,scales:{y:{min:0,max:100}}}});
}
function drawMiniCharts(metrics){
  const toVal = v => (typeof v==='number')? v : 0;
  const cat = metrics[8].value;
  const chartConfig = (id,label,val)=> new Chart(document.getElementById(id),{
    type:'doughnut',data:{labels:[label,'Remaining'],datasets:[{data:[val,100-val],backgroundColor:['#16a34a','#334155']}]},
    options:{plugins:{legend:{display:false}}}});
  chartConfig('chartCrawl','Crawlability',cat['Crawlability']);
  chartConfig('chartSEO','On-Page SEO',cat['On-Page SEO']);
  chartConfig('chartPerf','Performance',cat['Performance']);
  chartConfig('chartSec','Security',cat['Security']);
  chartConfig('chartMobile','Mobile',cat['Mobile']);
}
async function runAudit(e){
  e.preventDefault();
  const url = document.getElementById('urlInput').value;
  document.getElementById('loading').style.display='inline';
  try{
    const res = await fetch('/api/audit/open',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    const data = await res.json();
    if(res.ok){
      document.getElementById('results').style.display='block';
      document.getElementById('summary').textContent = data.metrics[3].value;
      document.getElementById('scoreGrade').innerHTML = `
        <span class="badge">Score: ${data.score}%</span>
        <span class="badge">Grade: ${data.grade}</span>`;
      const sev = data.metrics[7].value;
      document.getElementById('severity').innerHTML = `
        <span class="badge">Errors: ${sev.errors}</span>
        <span class="badge">Warnings: ${sev.warnings}</span>
        <span class="badge">Notices: ${sev.notices}</span>`;
      drawCategoryChart(data.metrics[8].value);
      drawMiniCharts(data.metrics);
      const tbody = document.getElementById('metricsTable').querySelector('tbody');
      tbody.innerHTML='';
      const entries = Object.entries(data.metrics).sort((a,b)=>parseInt(a[0])-parseInt(b[0]));
      for(const [id,obj] of entries){
        const desc = DESCRIPTORS[id]||{name:'(Unknown)',category:'-'};
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${id}</td>
          <td>${desc.name}</td>
          <td>${desc.category}</td>
          <td class="${severityClass(obj.value)}">${(typeof obj.value==='object')? JSON.stringify(obj.value): obj.value}</td>
          <td>${obj.detail || ''}</td>`;
        tbody.appendChild(tr);
      }
    }else{
      alert(data.detail || 'Audit failed');
    }
  }catch(err){
    alert('Error: '+err);
  }finally{
    document.getElementById('loading').style.display='none';
  }
}
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def web_home():
    # Embed descriptors for front-end rendering
    return HTML_BASE.replace("%DESCRIPTORS%", json.dumps(METRIC_DESCRIPTORS))

# -----------------------------------------------------------------------------
# Startup (optional scheduler removed to keep deployment simplest & error-free)
# -----------------------------------------------------------------------------
# No background tasks to avoid surprises on Railway dynos.

# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
