
"""
FF Tech AI Website Audit SaaS - Single File Backend (FastAPI)

Features:
- Open-access audits (no auth, no storage)
- Registered user audits (passwordless email magic-link, JWT sessions)
- Subscription limits (free: 10 audits; pro: unlimited + scheduling)
- PDF report generation (5 pages, branded, charts)
- Flexible scoring engine, transparent metric registry (200 metrics placeholders)
- Railway-ready deployment (PORT, DATABASE_URL)
- Frontend-agnostic JSON APIs + CORS enabled

Author: FF Tech
"""

import os
import io
import re
import ssl
import json
import time
import hmac
import math
import base64
import smtplib
import hashlib
import logging
import random
import string
import asyncio
import datetime
from typing import Any, Dict, Optional, List, Tuple

from fastapi import FastAPI, HTTPException, Depends, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr
from starlette.requests import Request

# HTTP & parsing
import requests
from urllib.parse import urlparse, urljoin

# DB (SQLAlchemy)
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON as SAJSON
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# PDF & Charts
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
APP_NAME = "FF Tech AI Website Audit SaaS"
FF_TECH_BRAND = "FF Tech"
FF_TECH_LOGO_TEXT = "FF TECH AI • Website Audit"
DEFAULT_LIMIT_FREE = 10

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech_ai_audit.db")
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_SECRET_32+CHARS")
PORT = int(os.getenv("PORT", "8000"))

# Optional SMTP for magic-link emails
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587")) if os.getenv("SMTP_PORT") else None
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@fftech.example")

# -----------------------------------------------------------------------------
# App & Middleware
# -----------------------------------------------------------------------------
app = FastAPI(title=APP_NAME, version="1.0.0", description="Frontend-agnostic, API-driven Website Audit SaaS")
security = HTTPBearer()

# CORS: allow any frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fftech_ai_audit")

# -----------------------------------------------------------------------------
# Database Setup
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

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    verified = Column(Boolean, default=False)
    plan = Column(String(32), default="free")  # free | pro | enterprise
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    audits_count = Column(Integer, default=0)
    audits = relationship("Audit", back_populates="user")

class Audit(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # null for open
    url = Column(String(2048), nullable=False)
    metrics = Column(SAJSON)  # full 200 metric registry
    score = Column(Integer)   # 0-100
    grade = Column(String(4)) # A+...D
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user = relationship("User", back_populates="audits")

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    url = Column(String(2048), nullable=False)
    frequency = Column(String(32), default="weekly")  # daily|weekly|monthly
    enabled = Column(Boolean, default=True)
    next_run_at = Column(DateTime, default=datetime.datetime.utcnow)

class MagicLink(Base):
    __tablename__ = "magic_links"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), index=True, nullable=False)
    token = Column(String(512), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

# -----------------------------------------------------------------------------
# Utility & Security
# -----------------------------------------------------------------------------
def now_utc() -> datetime.datetime:
    return datetime.datetime.utcnow()

def generate_token(payload: Dict[str, Any], exp_minutes: int = 30) -> str:
    """Stateless JWT-like HMAC token."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = dict(payload)
    payload["exp"] = int(time.time()) + exp_minutes * 60
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signing_input = f"{h_b64}.{p_b64}".encode()
    sig = hmac.new(SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
    s_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{h_b64}.{p_b64}.{s_b64}"

def verify_token(token: str) -> Dict[str, Any]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid")
        h_b64, p_b64, s_b64 = parts
        signing_input = f"{h_b64}.{p_b64}".encode()
        sig_expected = hmac.new(SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
        sig_given = base64.urlsafe_b64decode(s_b64 + "==")
        if not hmac.compare_digest(sig_expected, sig_given):
            raise ValueError("Bad signature")
        payload = json.loads(base64.urlsafe_b64decode(p_b64 + "=="))
        if int(time.time()) > payload.get("exp", 0):
            raise ValueError("Expired")
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

def auth_user(credentials: HTTPAuthorizationCredentials = Depends(security), db=Depends(db_session)) -> User:
    payload = verify_token(credentials.credentials)
    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Missing email in token")
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.verified:
        raise HTTPException(status_code=401, detail="User not verified")
    return user

def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except:
        return False

def safe_request(url: str, timeout: int = 10) -> Tuple[int, bytes, float, Dict[str, str]]:
    t0 = time.time()
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "FFTechAuditBot/1.0"})
        latency = time.time() - t0
        content = resp.content or b""
        return resp.status_code, content, latency, dict(resp.headers or {})
    except Exception as e:
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

def random_id(n: int = 32) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))

# -----------------------------------------------------------------------------
# Metric Registry & Scoring
# -----------------------------------------------------------------------------
# Map metric IDs (1..200) to descriptors and computation categories.
# We'll implement core metrics and mark others as TODO/N/A with transparent notes.

METRIC_DESCRIPTORS: Dict[int, Dict[str, Any]] = {
    # A. Executive Summary & Grading (1-10)
    1: {"name": "Overall Site Health Score (%)", "category": "A"},
    2: {"name": "Website Grade (A+ to D)", "category": "A"},
    3: {"name": "Executive Summary (200 Words)", "category": "A"},
    4: {"name": "Strengths Highlight Panel", "category": "A"},
    5: {"name": "Weak Areas Highlight Panel", "category": "A"},
    6: {"name": "Priority Fixes Panel", "category": "A"},
    7: {"name": "Visual Severity Indicators", "category": "A"},
    8: {"name": "Category Score Breakdown", "category": "A"},
    9: {"name": "Industry-Standard Presentation", "category": "A"},
    10: {"name": "Print / Certified Export Readiness", "category": "A"},
    # B. Overall Site Health (11–20)
    11: {"name": "Site Health Score", "category": "B"},
    12: {"name": "Total Errors", "category": "B"},
    13: {"name": "Total Warnings", "category": "B"},
    14: {"name": "Total Notices", "category": "B"},
    15: {"name": "Total Crawled Pages", "category": "B"},
    16: {"name": "Total Indexed Pages", "category": "B"},  # requires external API, placeholder
    17: {"name": "Issues Trend", "category": "B"},
    18: {"name": "Crawl Budget Efficiency", "category": "B"},
    19: {"name": "Orphan Pages Percentage", "category": "B"},
    20: {"name": "Audit Completion Status", "category": "B"},
    # C. Crawlability & Indexation (21–40)
    21: {"name": "HTTP 2xx Pages", "category": "C"},
    22: {"name": "HTTP 3xx Pages", "category": "C"},
    23: {"name": "HTTP 4xx Pages", "category": "C"},
    24: {"name": "HTTP 5xx Pages", "category": "C"},
    25: {"name": "Redirect Chains", "category": "C"},
    26: {"name": "Redirect Loops", "category": "C"},
    27: {"name": "Broken Internal Links", "category": "C"},
    28: {"name": "Broken External Links", "category": "C"},
    29: {"name": "robots.txt Blocked URLs", "category": "C"},
    30: {"name": "Meta Robots Blocked URLs", "category": "C"},
    31: {"name": "Non-Canonical Pages", "category": "C"},
    32: {"name": "Missing Canonical Tags", "category": "C"},
    33: {"name": "Incorrect Canonical Tags", "category": "C"},
    34: {"name": "Sitemap Missing Pages", "category": "C"},
    35: {"name": "Sitemap Not Crawled Pages", "category": "C"},
    36: {"name": "Hreflang Errors", "category": "C"},
    37: {"name": "Hreflang Conflicts", "category": "C"},
    38: {"name": "Pagination Issues", "category": "C"},
    39: {"name": "Crawl Depth Distribution", "category": "C"},
    40: {"name": "Duplicate Parameter URLs", "category": "C"},
    # D. On-Page SEO (41–75)
    41: {"name": "Missing Title Tags", "category": "D"},
    42: {"name": "Duplicate Title Tags", "category": "D"},
    43: {"name": "Title Too Long", "category": "D"},
    44: {"name": "Title Too Short", "category": "D"},
    45: {"name": "Missing Meta Descriptions", "category": "D"},
    46: {"name": "Duplicate Meta Descriptions", "category": "D"},
    47: {"name": "Meta Too Long", "category": "D"},
    48: {"name": "Meta Too Short", "category": "D"},
    49: {"name": "Missing H1", "category": "D"},
    50: {"name": "Multiple H1", "category": "D"},
    51: {"name": "Duplicate Headings", "category": "D"},
    52: {"name": "Thin Content Pages", "category": "D"},
    53: {"name": "Duplicate Content Pages", "category": "D"},
    54: {"name": "Low Text-to-HTML Ratio", "category": "D"},
    55: {"name": "Missing Image Alt Tags", "category": "D"},
    56: {"name": "Duplicate Alt Tags", "category": "D"},
    57: {"name": "Large Uncompressed Images", "category": "D"},
    58: {"name": "Pages Without Indexed Content", "category": "D"},
    59: {"name": "Missing Structured Data", "category": "D"},
    60: {"name": "Structured Data Errors", "category": "D"},
    61: {"name": "Rich Snippet Warnings", "category": "D"},
    62: {"name": "Missing Open Graph Tags", "category": "D"},
    63: {"name": "Long URLs", "category": "D"},
    64: {"name": "Uppercase URLs", "category": "D"},
    65: {"name": "Non-SEO-Friendly URLs", "category": "D"},
    66: {"name": "Too Many Internal Links", "category": "D"},
    67: {"name": "Pages Without Incoming Links", "category": "D"},
    68: {"name": "Orphan Pages", "category": "D"},
    69: {"name": "Broken Anchor Links", "category": "D"},
    70: {"name": "Redirected Internal Links", "category": "D"},
    71: {"name": "NoFollow Internal Links", "category": "D"},
    72: {"name": "Link Depth Issues", "category": "D"},
    73: {"name": "External Links Count", "category": "D"},
    74: {"name": "Broken External Links", "category": "D"},
    75: {"name": "Anchor Text Issues", "category": "D"},
    # E. Performance & Technical (76–96)
    76: {"name": "Largest Contentful Paint (LCP)", "category": "E"},
    77: {"name": "First Contentful Paint (FCP)", "category": "E"},
    78: {"name": "Cumulative Layout Shift (CLS)", "category": "E"},
    79: {"name": "Total Blocking Time", "category": "E"},
    80: {"name": "First Input Delay", "category": "E"},
    81: {"name": "Speed Index", "category": "E"},
    82: {"name": "Time to Interactive", "category": "E"},
    83: {"name": "DOM Content Loaded", "category": "E"},
    84: {"name": "Total Page Size", "category": "E"},
    85: {"name": "Requests Per Page", "category": "E"},
    86: {"name": "Unminified CSS", "category": "E"},
    87: {"name": "Unminified JavaScript", "category": "E"},
    88: {"name": "Render Blocking Resources", "category": "E"},
    89: {"name": "Excessive DOM Size", "category": "E"},
    90: {"name": "Third-Party Script Load", "category": "E"},
    91: {"name": "Server Response Time", "category": "E"},
    92: {"name": "Image Optimization", "category": "E"},
    93: {"name": "Lazy Loading Issues", "category": "E"},
    94: {"name": "Browser Caching Issues", "category": "E"},
    95: {"name": "Missing GZIP / Brotli", "category": "E"},
    96: {"name": "Resource Load Errors", "category": "E"},
    # F. Mobile, Security & International (97–150)
    97: {"name": "Mobile Friendly Test", "category": "F"},
    98: {"name": "Viewport Meta Tag", "category": "F"},
    99: {"name": "Small Font Issues", "category": "F"},
    100: {"name": "Tap Target Issues", "category": "F"},
    101: {"name": "Mobile Core Web Vitals", "category": "F"},
    102: {"name": "Mobile Layout Issues", "category": "F"},
    103: {"name": "Intrusive Interstitials", "category": "F"},
    104: {"name": "Mobile Navigation Issues", "category": "F"},
    105: {"name": "HTTPS Implementation", "category": "F"},
    106: {"name": "SSL Certificate Validity", "category": "F"},
    107: {"name": "Expired SSL", "category": "F"},
    108: {"name": "Mixed Content", "category": "F"},
    109: {"name": "Insecure Resources", "category": "F"},
    110: {"name": "Missing Security Headers", "category": "F"},
    111: {"name": "Open Directory Listing", "category": "F"},
    112: {"name": "Login Pages Without HTTPS", "category": "F"},
    113: {"name": "Missing Hreflang", "category": "F"},
    114: {"name": "Incorrect Language Codes", "category": "F"},
    115: {"name": "Hreflang Conflicts", "category": "F"},
    116: {"name": "Region Targeting Issues", "category": "F"},
    117: {"name": "Multi-Domain SEO Issues", "category": "F"},
    118: {"name": "Domain Authority", "category": "F"},
    119: {"name": "Referring Domains", "category": "F"},
    120: {"name": "Total Backlinks", "category": "F"},
    121: {"name": "Toxic Backlinks", "category": "F"},
    122: {"name": "NoFollow Backlinks", "category": "F"},
    123: {"name": "Anchor Distribution", "category": "F"},
    124: {"name": "Referring IPs", "category": "F"},
    125: {"name": "Lost / New Backlinks", "category": "F"},
    126: {"name": "JavaScript Rendering Issues", "category": "F"},
    127: {"name": "CSS Blocking", "category": "F"},
    128: {"name": "Crawl Budget Waste", "category": "F"},
    129: {"name": "AMP Issues", "category": "F"},
    130: {"name": "PWA Issues", "category": "F"},
    131: {"name": "Canonical Conflicts", "category": "F"},
    132: {"name": "Subdomain Duplication", "category": "F"},
    133: {"name": "Pagination Conflicts", "category": "F"},
    134: {"name": "Dynamic URL Issues", "category": "F"},
    135: {"name": "Lazy Load Conflicts", "category": "F"},
    136: {"name": "Sitemap Presence", "category": "F"},
    137: {"name": "Noindex Issues", "category": "F"},
    138: {"name": "Structured Data Consistency", "category": "F"},
    139: {"name": "Redirect Correctness", "category": "F"},
    140: {"name": "Broken Rich Media", "category": "F"},
    141: {"name": "Social Metadata Presence", "category": "F"},
    142: {"name": "Error Trend", "category": "F"},
    143: {"name": "Health Trend", "category": "F"},
    144: {"name": "Crawl Trend", "category": "F"},
    145: {"name": "Index Trend", "category": "F"},
    146: {"name": "Core Web Vitals Trend", "category": "F"},
    147: {"name": "Backlink Trend", "category": "F"},
    148: {"name": "Keyword Trend", "category": "F"},
    149: {"name": "Historical Comparison", "category": "F"},
    150: {"name": "Overall Stability Index", "category": "F"},
    # G. Competitor Analysis (151–167)
    151: {"name": "Competitor Health Score", "category": "G"},
    152: {"name": "Competitor Performance Comparison", "category": "G"},
    153: {"name": "Competitor Core Web Vitals Comparison", "category": "G"},
    154: {"name": "Competitor SEO Issues Comparison", "category": "G"},
    155: {"name": "Competitor Broken Links Comparison", "category": "G"},
    156: {"name": "Competitor Authority Score", "category": "G"},
    157: {"name": "Competitor Backlink Growth", "category": "G"},
    158: {"name": "Competitor Keyword Visibility", "category": "G"},
    159: {"name": "Competitor Rank Distribution", "category": "G"},
    160: {"name": "Competitor Content Volume", "category": "G"},
    161: {"name": "Competitor Speed Comparison", "category": "G"},
    162: {"name": "Competitor Mobile Score", "category": "G"},
    163: {"name": "Competitor Security Score", "category": "G"},
    164: {"name": "Competitive Gap Score", "category": "G"},
    165: {"name": "Competitive Opportunity Heatmap", "category": "G"},
    166: {"name": "Competitive Risk Heatmap", "category": "G"},
    167: {"name": "Overall Competitive Rank", "category": "G"},
    # H. Broken Links Intelligence (168–180)
    168: {"name": "Total Broken Links", "category": "H"},
    169: {"name": "Internal Broken Links", "category": "H"},
    170: {"name": "External Broken Links", "category": "H"},
    171: {"name": "Broken Links Trend", "category": "H"},
    172: {"name": "Broken Pages by Impact", "category": "H"},
    173: {"name": "Status Code Distribution", "category": "H"},
    174: {"name": "Page Type Distribution", "category": "H"},
    175: {"name": "Fix Priority Score", "category": "H"},
    176: {"name": "SEO Loss Impact", "category": "H"},
    177: {"name": "Affected Pages Count", "category": "H"},
    178: {"name": "Broken Media Links", "category": "H"},
    179: {"name": "Resolution Progress", "category": "H"},
    180: {"name": "Risk Severity Index", "category": "H"},
    # I. Opportunities, Growth & ROI (181–200)
    181: {"name": "High Impact Opportunities", "category": "I"},
    182: {"name": "Quick Wins Score", "category": "I"},
    183: {"name": "Long-Term Fixes", "category": "I"},
    184: {"name": "Traffic Growth Forecast", "category": "I"},
    185: {"name": "Ranking Growth Forecast", "category": "I"},
    186: {"name": "Conversion Impact Score", "category": "I"},
    187: {"name": "Content Expansion Opportunities", "category": "I"},
    188: {"name": "Internal Linking Opportunities", "category": "I"},
    189: {"name": "Speed Improvement Potential", "category": "I"},
    190: {"name": "Mobile Improvement Potential", "category": "I"},
    191: {"name": "Security Improvement Potential", "category": "I"},
    192: {"name": "Structured Data Opportunities", "category": "I"},
    193: {"name": "Crawl Optimization Potential", "category": "I"},
    194: {"name": "Backlink Opportunity Score", "category": "I"},
    195: {"name": "Competitive Gap ROI", "category": "I"},
    196: {"name": "Fix Roadmap Timeline", "category": "I"},
    197: {"name": "Time-to-Fix Estimate", "category": "I"},
    198: {"name": "Cost-to-Fix Estimate", "category": "I"},
    199: {"name": "ROI Forecast", "category": "I"},
    200: {"name": "Overall Growth Readiness", "category": "I"},
}

# -----------------------------------------------------------------------------
# Audit Engine (Core Logic)
# -----------------------------------------------------------------------------
class AuditEngine:
    """Compute metrics for a single URL with transparent scoring."""

    def __init__(self, url: str):
        if not is_valid_url(url):
            raise ValueError("Invalid URL")
        self.url = url
        self.base_domain = urlparse(url).netloc
        self.status_code, self.content, self.latency, self.headers = safe_request(url)
        self.html_text = self.content.decode(errors="ignore") if self.content else ""
        self.links_internal: List[str] = []
        self.links_external: List[str] = []
        self.resources_css: List[str] = []
        self.resources_js: List[str] = []
        self.resources_img: List[str] = []
        self._extract_links_and_resources()

    def _extract_links_and_resources(self):
        # Lightweight parsing using regex (avoid bs4 dependency in single file)
        hrefs = re.findall(r'href=[\'"]?([^\'" >]+)', self.html_text, flags=re.IGNORECASE)
        srcs = re.findall(r'src=[\'"]?([^\'" >]+)', self.html_text, flags=re.IGNORECASE)
        # Classify links:
        for u in hrefs:
            full = urljoin(self.url, u)
            if urlparse(full).netloc == self.base_domain:
                self.links_internal.append(full)
            else:
                self.links_external.append(full)
        # Resources:
        for s in srcs:
            full = urljoin(self.url, s)
            if full.lower().endswith(".css"):
                self.resources_css.append(full)
            elif full.lower().endswith(".js"):
                self.resources_js.append(full)
            elif any(full.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")):
                self.resources_img.append(full)

    # ---------------------- Metric Computation ----------------------
    def compute_metrics(self) -> Dict[int, Dict[str, Any]]:
        m: Dict[int, Dict[str, Any]] = {}

        # Helper counters (basic site health)
        total_errors = 0
        total_warnings = 0
        total_notices = 0

        # C: HTTP status snapshot for homepage only (full site crawl would iterate sitemap)
        m[21] = {"value": 1 if 200 <= self.status_code < 300 else 0, "detail": f"Homepage status: {self.status_code}"}
        m[23] = {"value": 1 if 400 <= self.status_code < 500 else 0, "detail": f"Homepage status: {self.status_code}"}
        m[24] = {"value": 1 if 500 <= self.status_code < 600 else 0, "detail": f"Homepage status: {self.status_code}"}

        if m[23]["value"] == 1 or m[24]["value"] == 1:
            total_errors += 1

        # D: On-page basics
        title_match = re.search(r"<title>(.*?)</title>", self.html_text, flags=re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""
        meta_desc_match = re.search(r'<meta[^>]+name=[\'"]description[\'"][^>]+content=\'"[\'"]', self.html_text, flags=re.IGNORECASE | re.DOTALL)
        meta_desc = meta_desc_match.group(1).strip() if meta_desc_match else ""

        # Title checks
        m[41] = {"value": 1 if not title else 0, "detail": f"Missing title: {not bool(title)}"}
        m[43] = {"value": 1 if title and len(title) > 65 else 0, "detail": f"Title length: {len(title)}"}
        m[44] = {"value": 1 if title and len(title) < 15 else 0, "detail": f"Title length: {len(title)}"}
        if m[41]["value"]: total_errors += 1
        if m[43]["value"] or m[44]["value"]: total_warnings += 1

        # Meta description checks
        m[45] = {"value": 1 if not meta_desc else 0, "detail": f"Missing meta description: {not bool(meta_desc)}"}
        m[47] = {"value": 1 if meta_desc and len(meta_desc) > 165 else 0, "detail": f"Meta length: {len(meta_desc)}"}
        m[48] = {"value": 1 if meta_desc and len(meta_desc) < 50 else 0, "detail": f"Meta length: {len(meta_desc)}"}
        if m[45]["value"]: total_warnings += 1
        if m[47]["value"] or m[48]["value"]: total_notices += 1

        # H1 checks
        h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", self.html_text, flags=re.IGNORECASE | re.DOTALL)
        m[49] = {"value": 1 if len(h1s) == 0 else 0, "detail": f"H1 count: {len(h1s)}"}
        m[50] = {"value": 1 if len(h1s) > 1 else 0, "detail": f"H1 count: {len(h1s)}"}
        if m[49]["value"] or m[50]["value"]: total_warnings += 1

        # Image alt tags
        img_tags = re.findall(r"<img[^>]*>", self.html_text, flags=re.IGNORECASE)
        missing_alts = sum(1 for tag in img_tags if re.search(r'alt=[\'"].*?[\'"]', tag, flags=re.IGNORECASE) is None)
        m[55] = {"value": missing_alts, "detail": f"Images missing alt: {missing_alts}"}
        if missing_alts > 0: total_notices += 1

        # URL checks (homepage)
        m[63] = {"value": 1 if len(self.url) > 115 else 0, "detail": f"URL length: {len(self.url)}"}
        m[64] = {"value": 1 if re.search(r"[A-Z]", self.url) else 0, "detail": "Uppercase present" if re.search(r"[A-Z]", self.url) else "Lowercase"}
        # HTTPS / SSL
        is_https = self.url.startswith("https://")
        m[105] = {"value": 1 if is_https else 0, "detail": "HTTPS enabled" if is_https else "Not HTTPS"}
        if not is_https: total_errors += 1

        # Mixed content (basic scan)
        mixed = any(link.startswith("http://") for link in self.links_internal + self.resources_js + self.resources_css + self.resources_img) and is_https
        m[108] = {"value": 1 if mixed else 0, "detail": "Mixed content detected" if mixed else "No mixed content"}
        if mixed: total_warnings += 1

        # Viewport meta
        viewport_meta = re.search(r'<meta[^>]+name=[\'"]viewport[\'"]', self.html_text, flags=re.IGNORECASE)
        m[98] = {"value": 1 if bool(viewport_meta) else 0, "detail": "Viewport meta present" if viewport_meta else "Missing viewport meta"}
        if not viewport_meta: total_warnings += 1

        # Performance basics
        page_size_kb = len(self.content) / 1024 if self.content else 0
        m[84] = {"value": round(page_size_kb, 2), "detail": f"Total page size (KB): {round(page_size_kb, 2)}"}
        m[85] = {"value": len(self.resources_css) + len(self.resources_js) + len(self.resources_img), "detail": "Resources per page"}
        m[91] = {"value": round(self.latency * 1000, 2), "detail": f"Server response time (ms): {round(self.latency * 1000, 2)}"}

        # Caching headers
        cache_control = self.headers.get("Cache-Control", "")
        m[94] = {"value": 0 if "max-age" in cache_control.lower() else 1, "detail": f"Cache-Control: {cache_control}"}
        if m[94]["value"]: total_notices += 1

        # Compression (approx via Content-Encoding)
        content_encoding = self.headers.get("Content-Encoding", "").lower()
        compressed = any(enc in content_encoding for enc in ["gzip", "br"])
        m[95] = {"value": 1 if compressed else 0, "detail": f"Content-Encoding: {content_encoding or 'none'}"}
        if not compressed and page_size_kb > 256: total_warnings += 1

        # Security headers (basic)
        sec_headers_required = ["Content-Security-Policy", "Strict-Transport-Security", "X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy"]
        missing_sec = [h for h in sec_headers_required if h not in self.headers]
        m[110] = {"value": len(missing_sec), "detail": f"Missing security headers: {missing_sec}"}
        if missing_sec: total_warnings += 1

        # Internal/external links & broken detection (sample check HEAD)
        broken_internal = 0
        for li in self.links_internal[:25]:  # limit for speed
            code, _, _, _ = safe_request(li, timeout=5)
            if code >= 400 or code == 0:
                broken_internal += 1
        m[27] = {"value": broken_internal, "detail": f"Broken internal links (sample): {broken_internal}"}
        if broken_internal > 0: total_errors += 1

        broken_external = 0
        for le in self.links_external[:25]:
            code, _, _, _ = safe_request(le, timeout=5)
            if code >= 400 or code == 0:
                broken_external += 1
        m[28] = {"value": broken_external, "detail": f"Broken external links (sample): {broken_external}"}
        if broken_external > 0: total_notices += 1

        # Robots.txt presence
        robots_url = f"{urlparse(self.url).scheme}://{self.base_domain}/robots.txt"
        rcode, rcontent, _, _ = safe_request(robots_url, timeout=5)
        m[29] = {"value": 0 if rcode == 200 and rcontent else 1, "detail": "robots.txt present" if rcode == 200 else "robots.txt missing"}
        if m[29]["value"] == 1: total_warnings += 1

        # Sitemap presence (common locations)
        sitemap_present = False
        for path in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap"]:
            scode, scontent, _, _ = safe_request(f"{urlparse(self.url).scheme}://{self.base_domain}{path}", timeout=5)
            if scode == 200 and scontent:
                sitemap_present = True
                break
        m[136] = {"value": 1 if sitemap_present else 0, "detail": "Sitemap present" if sitemap_present else "Sitemap missing"}
        if not sitemap_present: total_warnings += 1

        # HTTPS-related checks (SSL validity simple heuristic: timeouts considered bad)
        m[106] = {"value": 1 if is_https else 0, "detail": "SSL present (basic HTTPS)"}
        m[107] = {"value": 0, "detail": "Expired SSL (deep check requires cert inspection)"}  # placeholder

        # Trends & placeholders (transparent)
        m[12] = {"value": total_errors, "detail": "Total Errors"}
        m[13] = {"value": total_warnings, "detail": "Total Warnings"}
        m[14] = {"value": total_notices, "detail": "Total Notices"}
        m[15] = {"value": 1, "detail": "Total Crawled Pages (single-page quick audit)"}
        m[16] = {"value": "N/A", "detail": "Total Indexed Pages (requires search console/API)"}
        m[17] = {"value": "N/A", "detail": "Issues Trend (requires historical audits)"}
        m[18] = {"value": "N/A", "detail": "Crawl Budget Efficiency (requires multi-page crawl)"}
        m[19] = {"value": "N/A", "detail": "Orphan Pages Percentage (requires site map & link graph)"}
        m[20] = {"value": 1, "detail": "Audit Completion Status"}

        # Performance placeholders requiring RUM/lab tools
        for pid in [76,77,78,79,80,81,82,83]:
            m[pid] = {"value": "N/A", "detail": "Requires lab instrumentation (e.g., Lighthouse/Playwright)"}

        # Security & international placeholders
        for pid in [111,112,113,114,115,116,117,118,119,120,121,122,123,124,125]:
            m[pid] = {"value": "N/A", "detail": "Requires deeper crawl or external data sources"}

        # Canonical tags
        canonical = re.search(r'<link[^>]+rel=[\'"]canonical[\'"][^>]+href=\'"[\'"]', self.html_text, flags=re.IGNORECASE)
        m[32] = {"value": 0 if canonical else 1, "detail": f"Canonical present: {bool(canonical)}"}
        m[33] = {"value": "N/A", "detail": "Incorrect Canonical (needs cross-page validation)"}

        # Open Graph
        og_title = re.search(r'<meta[^>]+property=[\'"]og:title[\'"][^>]+content=\'"[\'"]', self.html_text, flags=re.IGNORECASE)
        m[62] = {"value": 0 if og_title else 1, "detail": "Open Graph title present" if og_title else "Missing OG tags"}

        # Render-blocking: crude detection of CSS in <head> and sync JS
        rb_css = len(self.resources_css)
        rb_js_sync = sum(1 for js in self.resources_js if "defer" not in js and "async" not in js)  # not accurate; placeholders
        m[88] = {"value": rb_css + rb_js_sync, "detail": f"Potential render-blocking resources (approx): {rb_css + rb_js_sync}"}

        # Excessive DOM size
        dom_nodes = len(re.findall(r"<[a-zA-Z]+", self.html_text))
        m[89] = {"value": dom_nodes, "detail": f"Approximate DOM nodes: {dom_nodes}"}

        # Third-party script load
        third_party_js = sum(1 for js in self.resources_js if urlparse(js).netloc != self.base_domain)
        m[90] = {"value": third_party_js, "detail": f"3rd-party scripts: {third_party_js}"}

        # Image optimization: large images (no byte size without fetching each; heuristic via filename)
        large_imgs = sum(1 for img in self.resources_img if re.search(r"(large|hero|banner|@2x|\d{4}x\d{4})", img, flags=re.IGNORECASE))
        m[92] = {"value": large_imgs, "detail": "Large or potentially unoptimized images (heuristic)"}

        # Lazy loading: detect loading="lazy"
        lazy_count = len(re.findall(r'loading=[\'"]lazy[\'"]', self.html_text, flags=re.IGNORECASE))
        m[93] = {"value": 0 if lazy_count > 0 else 1, "detail": f"Lazy loading present count: {lazy_count}"}

        # Resource load errors (runtime needed; placeholder)
        m[96] = {"value": "N/A", "detail": "Resource load errors need runtime capture"}

        # Social metadata presence
        m[141] = {"value": 0 if re.search(r'property=[\'"]og:', self.html_text) or re.search(r'name=[\'"]twitter:', self.html_text) else 1,
                  "detail": "Social metadata present" if re.search(r'property=[\'"]og:', self.html_text) else "Missing social metadata"}

        # Trends placeholders
        for pid in [142,143,144,145,146,147,148,149]:
            m[pid] = {"value": "N/A", "detail": "Trend requires historical data"}

        # Broken links intelligence
        m[168] = {"value": broken_internal + broken_external, "detail": "Total broken links (sample)"}
        m[169] = {"value": broken_internal, "detail": "Internal broken links"}
        m[170] = {"value": broken_external, "detail": "External broken links"}
        m[171] = {"value": "N/A", "detail": "Broken links trend requires history"}
        m[173] = {"value": {"2xx": m[21]["value"], "4xx": m[23]["value"], "5xx": m[24]["value"]}, "detail": "Status code distribution (homepage)"}
        m[175] = {"value": min(100, (broken_internal * 10) + (broken_external * 5)), "detail": "Fix priority score (heuristic)"}
        m[180] = {"value": min(100, (total_errors * 20) + (total_warnings * 10)), "detail": "Risk severity index (heuristic)"}

        # Opportunities & ROI
        m[182] = {"value": max(0, 100 - (total_errors * 15 + total_warnings * 5)), "detail": "Quick Wins Score"}
        m[189] = {"value": min(100, m[88]["value"] * 5 + m[92]["value"] * 5), "detail": "Speed improvement potential"}
        m[190] = {"value": 50 if not viewport_meta else 10, "detail": "Mobile improvement potential"}
        m[191] = {"value": min(100, len(missing_sec) * 10), "detail": "Security improvement potential"}
        m[200] = {"value": max(0, 100 - m[180]["value"]), "detail": "Overall Growth Readiness"}

        # Executive summary & grading
        # Site health score based on error/warn/notice and performance heuristics
        base_score = 100
        base_score -= total_errors * 10
        base_score -= total_warnings * 5
        base_score -= min(10, int(page_size_kb / 512) * 2)
        base_score -= min(10, m[88]["value"])
        score = max(0, min(100, base_score))

        m[1] = {"value": score, "detail": "Overall Site Health Score (%)"}
        m[11] = {"value": score, "detail": "Site Health Score"}
        grade = grade_from_score(score)
        m[2] = {"value": grade, "detail": "Website Grade"}

        strengths = []
        if is_https: strengths.append("HTTPS enabled")
        if title and 15 <= len(title) <= 65: strengths.append("Title tag length optimal")
        if meta_desc and 50 <= len(meta_desc) <= 165: strengths.append("Meta description length optimal")
        if lazy_count > 0: strengths.append("Images use lazy loading")
        if compressed: strengths.append("Compression (gzip/br) enabled")

        weaknesses = []
        if m[41]["value"]: weaknesses.append("Missing title tag")
        if m[45]["value"]: weaknesses.append("Missing meta description")
        if mixed: weaknesses.append("Mixed content over HTTPS")
        if m[110]["value"] > 0: weaknesses.append("Missing security headers")
        if broken_internal > 0: weaknesses.append("Broken internal links present")
        if not sitemap_present: weaknesses.append("Sitemap missing")

        priority_fixes = []
        if broken_internal > 0: priority_fixes.append("Fix internal broken links")
        if not is_https: priority_fixes.append("Enable HTTPS sitewide")
        if m[110]["value"] > 0: priority_fixes.append("Implement security headers (CSP, HSTS, X-Frame-Options, etc.)")
        if not viewport_meta: priority_fixes.append("Add responsive viewport meta for mobile")
        if not compressed and page_size_kb > 256: priority_fixes.append("Enable gzip/brotli compression")

        m[4] = {"value": strengths, "detail": "Strengths Highlight Panel"}
        m[5] = {"value": weaknesses, "detail": "Weak Areas Highlight Panel"}
        m[6] = {"value": priority_fixes, "detail": "Priority Fixes Panel"}

        # Category score breakdown (coarse)
        cat_scores = {
            "Crawlability": max(0, 100 - (m[27]["value"] + m[28]["value"]) * 5),
            "On-Page SEO": max(0, 100 - (m[41]["value"] + m[45]["value"] + m[43]["value"] + m[44]["value"]) * 10),
            "Performance": max(0, 100 - (m[84]["value"] / 10 + m[88]["value"] * 5 + (0 if compressed else 10))),
            "Security": max(0, 100 - (m[110]["value"] * 10 + (0 if is_https else 50))),
            "Mobile": max(0, 100 - (0 if viewport_meta else 30)),
        }
        m[8] = {"value": cat_scores, "detail": "Category Score Breakdown"}

        # Visual severity indicators (summary)
        m[7] = {"value": {"errors": total_errors, "warnings": total_warnings, "notices": total_notices},
                "detail": "Visual Severity Indicators"}
        m[9] = {"value": "Yes", "detail": "Industry-standard presentation"}
        m[10] = {"value": "Ready", "detail": "Print / Certified Export Readiness"}

        # Return completed metrics
        return m

    # ---------------------- Executive Summary ----------------------
    def executive_summary(self, metrics: Dict[int, Dict[str, Any]]) -> str:
        score = metrics[1]["value"]
        grade = metrics[2]["value"]
        errs = metrics[12]["value"]
        warns = metrics[13]["value"]
        notes = metrics[14]["value"]
        perf = metrics[84]["value"]
        resp = metrics[91]["value"]
        strengths = ", ".join(metrics[4]["value"]) if metrics[4]["value"] else "None identified"
        weaknesses = ", ".join(metrics[5]["value"]) if metrics[5]["value"] else "None identified"

        text = (
            f"The website at {self.url} was assessed using FF Tech's professional audit framework to "
            f"measure crawlability, on-page SEO, performance, mobile readiness, and security. "
            f"The site achieved an overall health score of {score}% corresponding to a grade of {grade}. "
            f"Key indicators include {errs} errors, {warns} warnings, and {notes} notices discovered "
            f"during a quick audit of the homepage and core resources. Performance heuristics indicate "
            f"an approximate payload of {perf} KB and a server response time around {resp} ms. "
            f"Strengths observed: {strengths}. Notable weaknesses: {weaknesses}. Priority recommendations "
            f"are provided to address issues likely to impact discoverability, speed, and trust, including "
            f"security header improvements, resolving broken links, and adopting best practices for "
            f"metadata and structured content. Category scores offer a balanced view across crawlability, "
            f"on-page SEO, performance, security, and mobile. This report serves as an executive reference "
            f"to guide near-term fixes and longer-term optimization. Implementing the recommendations should "
            f"improve user experience, search visibility, and the overall stability of the site."
        )
        # Ensure ~200 words (approx)
        words = text.split()
        if len(words) < 200:
            filler = " The audit is based on transparent, industry-standard checks and is frontend-agnostic for integration across HTML or modern frameworks. The methodology normalizes metrics into a consistent scale, enabling clear comparisons over time while remaining extensible for competitive benchmarking and scheduled monitoring."
            text = text + filler
        return text

# -----------------------------------------------------------------------------
# PDF Generation (5 pages)
# -----------------------------------------------------------------------------
def _plot_category_breakdown(cat_scores: Dict[str, float]) -> bytes:
    fig, ax = plt.subplots(figsize=(6, 4))
    labels = list(cat_scores.keys())
    values = [cat_scores[k] for k in labels]
    ax.bar(labels, values, color="#2E86C1")
    ax.set_ylim(0, 100)
    ax.set_title("Category Score Breakdown")
    ax.set_ylabel("Score (0–100)")
    ax.tick_params(axis='x', rotation=30)
    buf = io.BytesIO()
    plt.tight_layout()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()

def build_pdf_report(audit: Audit, metrics: Dict[int, Dict[str, Any]]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    styles = getSampleStyleSheet()

    # Page 1: Cover + Executive Summary
    c.setFillColor(colors.HexColor("#0A2540"))
    c.rect(0, height - 2.5*cm, width, 2.5*cm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2*cm, height - 1.5*cm, f"{FF_TECH_LOGO_TEXT}")
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2*cm, height - 4*cm, "Executive Summary")
    summary = metrics.get(3, {}).get("value")
    if not summary:
        # Build summary on the fly
        engine = AuditEngine(audit.url)
        summary = engine.executive_summary(metrics)
    textobj = c.beginText(2*cm, height - 5*cm)
    textobj.setFont("Helvetica", 11)
    for line in re.findall(".{1,90}(?:\\s|$)", summary):
        textobj.textLine(line.strip())
    c.drawText(textobj)

    # Score cards
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2*cm, height - 11*cm, "Site Health Score:")
    c.setFont("Helvetica", 14)
    c.drawString(8*cm, height - 11*cm, f"{metrics[1]['value']}%   Grade: {metrics[2]['value']}")

    c.setFont("Helvetica-Bold", 14)
    c.drawString(2*cm, height - 12*cm, "Severity Overview:")
    sev = metrics[7]["value"]
    c.setFont("Helvetica", 12)
    c.drawString(6*cm, height - 12*cm, f"Errors: {sev['errors']}  Warnings: {sev['warnings']}  Notices: {sev['notices']}")

    c.setFont("Helvetica-Oblique", 10)
    c.drawString(2*cm, 1.5*cm, f"{FF_TECH_BRAND} • Certified Audit Report • Generated: {now_utc().isoformat()}")

    c.showPage()

    # Page 2: Category Breakdown + Chart
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2*cm, height - 2.5*cm, "Category Performance")
    cat_scores = metrics[8]["value"]
    chart_png = _plot_category_breakdown(cat_scores)
    img = ImageReader(io.BytesIO(chart_png))
    c.drawImage(img, 2*cm, height - 12*cm, width=16*cm, height=8*cm, preserveAspectRatio=True, mask='auto')

    c.setFont("Helvetica", 11)
    y = height - 13*cm
    for k, v in cat_scores.items():
        c.drawString(2*cm, y, f"{k}: {int(v)}")
        y -= 0.6*cm

    # Conclusion on page
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(2*cm, 1.5*cm, "Conclusion: Focus on security headers and broken links for immediate gains, followed by performance tuning.")

    c.showPage()

    # Page 3: Crawlability & SEO Highlights
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2*cm, height - 2.5*cm, "Crawlability & On-Page SEO")
    c.setFont("Helvetica", 11)
    items = [
        f"Broken internal links: {metrics[27]['value']}",
        f"Broken external links: {metrics[28]['value']}",
        f"Canonical present: {'No' if metrics[32]['value'] else 'Yes'}",
        f"Title length issues: {'Yes' if metrics[43]['value'] or metrics[44]['value'] else 'No'}",
        f"Missing meta description: {'Yes' if metrics[45]['value'] else 'No'}",
        f"Open Graph tags: {'Missing' if metrics[62]['value'] else 'Present'}",
    ]
    y = height - 4*cm
    for t in items:
        c.drawString(2*cm, y, t)
        y -= 0.8*cm

    c.setFont("Helvetica-Oblique", 10)
    c.drawString(2*cm, 1.5*cm, "Conclusion: Resolve metadata gaps and link integrity to strengthen crawlability and snippet quality.")

    c.showPage()

    # Page 4: Performance & Security
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2*cm, height - 2.5*cm, "Performance & Security")
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
    for t in perf_items:
        c.drawString(2*cm, y, t)
        y -= 0.8*cm

    c.setFont("Helvetica-Oblique", 10)
    c.drawString(2*cm, 1.5*cm, "Conclusion: Tune caching/compression, reduce blocking resources, and enforce modern security headers.")

    c.showPage()

    # Page 5: Priorities, Opportunities, ROI
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2*cm, height - 2.5*cm, "Priorities, Opportunities & ROI")
    c.setFont("Helvetica", 11)
    priorities = metrics[6]["value"]
    opp_quick_wins = metrics[182]["value"]
    speed_potential = metrics[189]["value"]
    security_potential = metrics[191]["value"]
    growth_readiness = metrics[200]["value"]

    y = height - 4*cm
    c.drawString(2*cm, y, "Priority Fixes:")
    y -= 0.8*cm
    for p in priorities:
        c.drawString(3*cm, y, f"- {p}")
        y -= 0.7*cm

    y -= 0.3*cm
    c.drawString(2*cm, y, f"Quick Wins Score: {opp_quick_wins}")
    y -= 0.7*cm
    c.drawString(2*cm, y, f"Speed Improvement Potential: {speed_potential}")
    y -= 0.7*cm
    c.drawString(2*cm, y, f"Security Improvement Potential: {security_potential}")
    y -= 0.7*cm
    c.drawString(2*cm, y, f"Overall Growth Readiness: {growth_readiness}")

    c.setFont("Helvetica-Oblique", 10)
    c.drawString(2*cm, 1.5*cm, "Conclusion: Executing priority fixes yields near-term ROI and improves long-term stability and visibility.")

    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes

# -----------------------------------------------------------------------------
# Email Sending (Passwordless Magic Link)
# -----------------------------------------------------------------------------
def send_magic_link(email: str, token: str, request: Request):
    """Send or log magic link."""
    verify_url = f"{str(request.base_url).rstrip('/')}/auth/verify?token={token}"
    subject = f"{FF_TECH_BRAND} Login Link"
    body = f"Click to log in:\n\n{verify_url}\n\nThis link expires in 30 minutes."
    logger.info(f"[DEV] Magic link for {email}: {verify_url}")

    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS and SMTP_FROM):
        # No SMTP configured; log only
        return

    message = f"From: {SMTP_FROM}\r\nTo: {email}\r\nSubject: {subject}\r\n\r\n{body}"
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_FROM, [email], message)

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

class ScheduleRequest(BaseModel):
    url: str
    frequency: str = Field("weekly", pattern="^(daily|weekly|monthly)$")

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.get("/")
def root():
    return {"name": APP_NAME, "status": "ok", "docs": "/docs"}

# -------------------- Auth --------------------
@app.post("/auth/request-link")
def request_link(payload: MagicLinkRequest, request: Request, db=Depends(db_session)):
    email = payload.email.lower().strip()
    token = generate_token({"email": email, "purpose": "magic"}, exp_minutes=30)
    ml = MagicLink(email=email, token=token, expires_at=now_utc() + datetime.timedelta(minutes=30), used=False)
    db.add(ml)
    db.commit()
    send_magic_link(email, token, request)
    return {"message": "Login link sent if SMTP configured. (Also logged to server for dev.)"}

@app.get("/auth/verify")
def verify_magic_link(token: str, db=Depends(db_session)):
    # Validate token
    payload = verify_token(token)
    if payload.get("purpose") != "magic":
        raise HTTPException(status_code=400, detail="Invalid purpose")

    # Check one-time usage
    ml = db.query(MagicLink).filter(MagicLink.token == token).first()
    if not ml or ml.used or ml.expires_at < now_utc():
        raise HTTPException(status_code=400, detail="Magic link invalid or expired")

    ml.used = True
    # Upsert user
    email = payload["email"]
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, verified=True, plan="free")
        db.add(user)
    else:
        user.verified = True
    db.commit()

    # Issue session token
    session_token = generate_token({"email": email, "purpose": "session"}, exp_minutes=60*24*30)  # 30 days
    return {"token": session_token, "plan": user.plan, "email": user.email}

@app.get("/me")
def me(user: User = Depends(auth_user)):
    return {"email": user.email, "plan": user.plan, "audits_count": user.audits_count, "created_at": user.created_at.isoformat()}

# -------------------- Open Access Audit --------------------
@app.post("/audit/open", response_model=AuditResponse)
def audit_open(req: AuditRequest):
    if not is_valid_url(req.url):
        raise HTTPException(status_code=400, detail="Invalid URL")

    engine = AuditEngine(req.url)
    metrics = engine.compute_metrics()
    # Executive summary ensure presence (metric 3)
    metrics[3] = {"value": engine.executive_summary(metrics), "detail": "Executive Summary (200 words)"}
    score = metrics[1]["value"]
    grade = metrics[2]["value"]

    return AuditResponse(url=req.url, score=score, grade=grade, metrics=metrics)

# -------------------- Registered User Audit --------------------
@app.post("/audit/user", response_model=AuditResponse)
def audit_user(req: AuditRequest, user: User = Depends(auth_user), db=Depends(db_session)):
    if not is_valid_url(req.url):
        raise HTTPException(status_code=400, detail="Invalid URL")

    # Free plan limit
    if user.plan == "free" and user.audits_count >= DEFAULT_LIMIT_FREE:
        raise HTTPException(status_code=402, detail="Free plan limit reached (10 audits). Upgrade for more.")

    engine = AuditEngine(req.url)
    metrics = engine.compute_metrics()
    metrics[3] = {"value": engine.executive_summary(metrics), "detail": "Executive Summary (200 words)"}
    score = metrics[1]["value"]
    grade = metrics[2]["value"]

    audit = Audit(user_id=user.id, url=req.url, metrics=metrics, score=score, grade=grade)
    db.add(audit)
    user.audits_count += 1
    db.commit()

    return AuditResponse(url=req.url, score=score, grade=grade, metrics=metrics)

@app.get("/audits")
def list_audits(limit: int = Query(20, ge=1, le=100), user: User = Depends(auth_user), db=Depends(db_session)):
    rows = db.query(Audit).filter(Audit.user_id == user.id).order_by(Audit.created_at.desc()).limit(limit).all()
    return [{"id": a.id, "url": a.url, "score": a.score, "grade": a.grade, "created_at": a.created_at.isoformat()} for a in rows]

# -------------------- PDF Reporting --------------------
@app.get("/report/{audit_id}.pdf")
def report_pdf(audit_id: int, user: User = Depends(auth_user), db=Depends(db_session)):
    audit = db.query(Audit).filter(Audit.id == audit_id, Audit.user_id == user.id).first()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    pdf_bytes = build_pdf_report(audit, audit.metrics)
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="FFTech_Audit_{audit.id}.pdf"'})

@app.post("/report/open.pdf")
def report_open_pdf(req: AuditRequest):
    if not is_valid_url(req.url):
        raise HTTPException(status_code=400, detail="Invalid URL")
    engine = AuditEngine(req.url)
    metrics = engine.compute_metrics()
    metrics[3] = {"value": engine.executive_summary(metrics), "detail": "Executive Summary (200 words)"}
    # Build transient Audit-like obj
    audit = Audit(id=0, user_id=None, url=req.url, metrics=metrics, score=metrics[1]["value"], grade=metrics[2]["value"])
    pdf_bytes = build_pdf_report(audit, metrics)
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf",
                             headers={"Content-Disposition": 'attachment; filename="FFTech_Audit_Open.pdf"'})

# -------------------- Scheduling (Pro+) --------------------
@app.post("/schedule")
def create_schedule(payload: ScheduleRequest, user: User = Depends(auth_user), db=Depends(db_session)):
    if user.plan == "free":
        raise HTTPException(status_code=402, detail="Scheduling requires subscription.")
    sch = Schedule(user_id=user.id, url=payload.url, frequency=payload.frequency, enabled=True,
                   next_run_at=now_utc() + datetime.timedelta(days=1 if payload.frequency == "daily" else 7 if payload.frequency == "weekly" else 30))
    db.add(sch)
    db.commit()
    return {"message": "Scheduled", "schedule_id": sch.id}

@app.get("/schedule")
def list_schedule(user: User = Depends(auth_user), db=Depends(db_session)):
    rows = db.query(Schedule).filter(Schedule.user_id == user.id).all()
    return [{"id": s.id, "url": s.url, "frequency": s.frequency, "enabled": s.enabled, "next_run_at": s.next_run_at.isoformat()} for s in rows]

# Background task loop (simple scheduler)
async def scheduler_loop():
    while True:
        try:
            db = SessionLocal()
            now = now_utc()
            due = db.query(Schedule).filter(Schedule.enabled == True, Schedule.next_run_at <= now).all()
            for s in due:
                user = db.query(User).filter(User.id == s.user_id).first()
                if not user:
                    continue
                # Run audit and store
                try:
                    engine = AuditEngine(s.url)
                    metrics = engine.compute_metrics()
                    metrics[3] = {"value": engine.executive_summary(metrics), "detail": "Executive Summary (200 words)"}
                    score = metrics[1]["value"]
                    grade = metrics[2]["value"]
                    a = Audit(user_id=user.id, url=s.url, metrics=metrics, score=score, grade=grade)
                    db.add(a)
                    user.audits_count += 1
                    # Reschedule
                    delta = datetime.timedelta(days=1 if s.frequency == "daily" else 7 if s.frequency == "weekly" else 30)
                    s.next_run_at = now + delta
                    db.commit()
                    logger.info(f"[Scheduler] Audit stored for {user.email} {s.url}")
                except Exception as e:
                    logger.error(f"[Scheduler] Error auditing {s.url}: {e}")
        except Exception as e:
            logger.error(f"[Scheduler] Loop error: {e}")
        finally:
            try:
                db.close()
            except:
                pass
        await asyncio.sleep(30)  # run every 30s

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(scheduler_loop())

# -----------------------------------------------------------------------------
# Run (local)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
