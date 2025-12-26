
# app.py
import os
import io
import json
import smtplib
from datetime import datetime, timedelta, time as time_only
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from email_validator import validate_email, EmailNotValidError
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from fastapi import FastAPI, Request, Depends, HTTPException, status, Body
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON as SAJSON
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session

from passlib.context import CryptContext
import jwt

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Optional: Pillow for fallback favicon
try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# ------------------ App & Config ------------------
app = FastAPI()
templates = Jinja2Templates(directory="templates")

if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./db.sqlite3")
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "roy.jamshaid@gmail.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Jamshaid,1981")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", ADMIN_EMAIL)
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8080")  # used in verify links

serializer = URLSafeTimedSerializer(SECRET_KEY)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
Base = declarative_base()

scheduler = BackgroundScheduler(timezone="UTC")


# ------------------ DB Models ------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    timezone = Column(String(64), default="UTC")  # IANA tz e.g., Asia/Karachi
    created_at = Column(DateTime, default=datetime.utcnow)

    audits = relationship("Audit", back_populates="user", cascade="all,delete")
    schedules = relationship("Schedule", back_populates="user", cascade="all,delete")


class Audit(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL for open audits
    url = Column(String(2048), nullable=False)

    # Scores
    site_health_score = Column(Integer, default=0)
    grade = Column(String(4), default="F")

    # Summary & findings
    metrics_summary_json = Column(Text, default="{}")
    top_issues_json = Column(Text, default="[]")
    executive_summary = Column(Text, default="")  # 200-word summary

    # Timing
    finished_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="audits")


class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    url = Column(String(2048), nullable=False)
    # daily time-of-day in user's timezone, cron stored in UTC scheduler
    hour_utc = Column(Integer, default=0)
    minute_utc = Column(Integer, default=0)
    enabled = Column(Boolean, default=True)
    report_type = Column(String(16), default="daily")  # daily | accumulated
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="schedules")


# ------------------ Utilities ------------------
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def send_email(to_email: str, subject: str, body: str, attachments: list[tuple[str, bytes]] | None = None):
    """
    Simple SMTP email (plaintext) with optional attachments.
    Attachments: list of (filename, bytes)
    """
    attachments = attachments or []
    boundary = "==FFTECH_BOUNDARY=="
    if SMTP_HOST and SMTP_USER and SMTP_PASS:
        message = []
        message.append(f"From: {SMTP_FROM}")
        message.append(f"To: {to_email}")
        message.append(f"Subject: {subject}")
        message.append("MIME-Version: 1.0")
        if attachments:
            message.append(f'Content-Type: multipart/mixed; boundary="{boundary}"\r\n')
            message.append(f"--{boundary}")
            message.append("Content-Type: text/plain; charset=utf-8")
            message.append("Content-Transfer-Encoding: 7bit\r\n")
            message.append(body + "\r\n")
            for fname, content in attachments:
                message.append(f"--{boundary}")
                message.append(f'Content-Type: application/pdf; name="{fname}"')
                message.append("Content-Transfer-Encoding: base64")
                message.append(f'Content-Disposition: attachment; filename="{fname}"\r\n')
                import base64
                b64 = base64.b64encode(content).decode("ascii")
                message.append(b64 + "\r\n")
            message.append(f"--{boundary}--")
        else:
            message.append("Content-Type: text/plain; charset=utf-8\r\n")
            message.append(body)
        full = "\r\n".join(message)
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_FROM, [to_email], full)
            print(f"[EMAIL] Sent to {to_email}")
        except Exception as e:
            print(f"[EMAIL] Failed: {e}\nSubject: {subject}\nBody:\n{body}")
    else:
        print(f"[EMAIL] SMTP not configured. Subject: {subject}\nTo: {to_email}\n{body}")


def send_verification_email(to_email: str, token: str):
    link = f"{PUBLIC_URL}/auth/verify?token={token}"
    subject = "Verify your FF Tech AI Audit account"
    body = f"Welcome to FF Tech!\n\nPlease verify your email by clicking the link below:\n{link}\n\nLink expires in 24 hours."
    send_email(to_email, subject, body)


def generate_favicon_bytes() -> bytes:
    if PIL_AVAILABLE:
        img = Image.new("RGBA", (32, 32), (99, 102, 241, 255))
        draw = ImageDraw.Draw(img)
        draw.ellipse((6, 6, 26, 26), outline=(255, 255, 255, 220), width=2)
        buf = io.BytesIO()
        img.save(buf, format="ICO"); buf.seek(0)
        return buf.getvalue()
    return b"\x00\x00\x01\x00\x01\x00\x10\x10\x00\x00\x01\x00\x04\x00(\x01\x00\x00\x16\x00\x00\x00" + b"\x00" * 64


# ------------------ Audit Engine (60+ metrics) ------------------
def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return raw
    parsed = urlparse(raw)
    if not parsed.scheme:
        raw = "https://" + raw  # prefer HTTPS
    return raw


def safe_request(url: str, method: str = "GET", **kwargs) -> requests.Response | None:
    try:
        kwargs.setdefault("timeout", (8, 16))
        kwargs.setdefault("allow_redirects", True)
        kwargs.setdefault("headers", {"User-Agent": "FFTech-AuditBot/1.1 (+https://fftech.example)"})
        return requests.request(method.upper(), url, **kwargs)
    except Exception:
        return None


def grade_from_score(score: int) -> str:
    if score >= 95: return "A+"
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"


def pct(n: int, d: int) -> float:
    return (n / d * 100.0) if d else 0.0


def detect_mixed_content(soup: BeautifulSoup, page_scheme: str) -> bool:
    if page_scheme != "https": return False
    for tag in soup.find_all(["img", "script", "link", "iframe", "video", "audio", "source"]):
        for attr in ["src", "href", "data", "poster"]:
            val = tag.get(attr)
            if isinstance(val, str) and val.startswith("http://"):
                return True
    return False


def is_blocking_script(tag) -> bool:
    if tag.name != "script": return False
    if tag.get("type") == "module": return False
    return not (tag.get("async") or tag.get("defer"))


def crawl_internal(seed_url: str, max_pages: int = 30) -> list[dict]:
    """
    Crawl up to max_pages internal pages.
    Returns list of {url, status, final_url, redirects, size_bytes, ttfb_ms}
    """
    visited, queue, results, host = set(), [seed_url], [], urlparse(seed_url).netloc
    while queue and len(results) < max_pages:
        url = queue.pop(0)
        if url in visited: continue
        visited.add(url)
        resp = safe_request(url, "GET")
        if not resp:
            results.append({"url": url, "status": None, "final_url": url, "redirects": 0, "size_bytes": 0, "ttfb_ms": 0})
            continue
        final = resp.url
        redirs = len(resp.history) if resp.history else 0
        ttfb = int(resp.elapsed.total_seconds() * 1000)
        size = len(resp.content or b"")
        results.append({"url": url, "status": resp.status_code, "final_url": final, "redirects": redirs, "size_bytes": size, "ttfb_ms": ttfb})

        # Extract more internal links to crawl
        try:
            soup = BeautifulSoup(resp.text or "", "html.parser")
            for a in soup.find_all("a"):
                href = a.get("href") or ""
                if not href: continue
                abs_url = urljoin(final, href)
                parsed = urlparse(abs_url)
                if parsed.netloc == host and parsed.scheme in ("http", "https"):
                    # Normalize
                    if abs_url not in visited and abs_url not in queue:
                        queue.append(abs_url)
                # limit queue growth
                if len(queue) > max_pages * 3:
                    queue = queue[:max_pages * 3]
        except Exception:
            pass
    return results


def audit_website(url: str, deep_crawl_pages: int = 20) -> dict:
    """
    Performs a multi-category audit with 60+ metrics and strict scoring.
    Returns dict with `audit` and `previous_audit` (None on SSR unless wired).
    """
    url = normalize_url(url)
    resp = safe_request(url, "GET")
    errors: list[dict] = []; warnings: list[dict] = []; notices: list[dict] = []

    status_code = resp.status_code if resp else None
    final_url = resp.url if resp else url
    headers = dict(resp.headers) if resp else {}
    elapsed_ms = int(resp.elapsed.total_seconds() * 1000) if resp else 0
    html = resp.text if (resp and resp.text) else ""
    page_size_bytes = len(resp.content) if resp else 0
    page_scheme = urlparse(final_url).scheme or "https"

    # If homepage fails
    if not resp or (status_code and status_code >= 400):
        errors.append({"name": "Homepage unreachable or error status", "severity": "high",
                       "suggestion": "Fix DNS/TLS/server errors; homepage must return 200."})
        ms = {
            "total_errors": len(errors), "total_warnings": 0, "total_notices": 0,
            "performance_score": 0, "seo_score": 0, "accessibility_score": 0,
            "best_practices_score": 0, "security_score": 0,
            "pages_crawled": 0, "largest_contentful_paint_ms": 0,
            "first_input_delay_ms": 0, "core_web_vitals_pass_rate_%": 0,
        }
        site_health_score = 0
        audit = {
            "website": {"url": url},
            "site_health_score": site_health_score,
            "grade": grade_from_score(site_health_score),
            "competitors": [],
            "top_issues": errors,
            "metrics_summary": ms,
            "recommendations": _default_recommendations(),
            "weaknesses": [e["name"] for e in errors],
            "finished_at": datetime.now().strftime("%b %d, %Y %H:%M"),
            "executive_summary": "Homepage is unreachable; fix server configuration, DNS, TLS, and availability before proceeding.",
        }
        return {"audit": audit, "previous_audit": None}

    soup = BeautifulSoup(html, "html.parser")

    # ----------------- Metrics collection -----------------
    # SEO & On-page
    title_tag = soup.title.string.strip() if soup.title and soup.title.string else ""
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_desc = (meta_desc_tag.get("content") or "").strip() if meta_desc_tag else ""
    h1_tags = soup.find_all("h1"); h1_count = len(h1_tags)
    canonical_link = soup.find("link", rel=lambda v: v and "canonical" in v.lower())
    lang_attr = soup.html.get("lang") if soup.html else None
    robots_meta_tag = soup.find("meta", attrs={"name": "robots"})
    robots_meta = (robots_meta_tag.get("content") or "").lower().strip() if robots_meta_tag else ""

    img_tags = soup.find_all("img")
    total_imgs = len(img_tags)
    imgs_without_alt = len([i for i in img_tags if not (i.get("alt") and i.get("alt").strip())])
    ld_json_count = len(soup.find_all("script", attrs={"type": "application/ld+json"}))
    og_meta = soup.find("meta", property=lambda v: v and v.startswith("og:"))
    twitter_meta = soup.find("meta", attrs={"name": lambda v: v and v.startswith("twitter:")})

    # URLs & internal links
    a_tags = soup.find_all("a")
    parsed_netloc = urlparse(final_url).netloc
    internal_links = 0; external_links = 0; broken_internal = 0; broken_external = 0
    for a in a_tags:
        href = a.get("href") or ""
        if not href: continue
        abs_url = urljoin(final_url, href)
        netloc = urlparse(abs_url).netloc
        if href.startswith("#") or netloc == parsed_netloc:
            internal_links += 1
        else:
            external_links += 1
        # quick HEAD check for broken
        head = safe_request(abs_url, "HEAD")
        if not head or (head.status_code and head.status_code >= 400):
            if netloc == parsed_netloc or href.startswith("#"):
                broken_internal += 1
            else:
                broken_external += 1

    # Performance / CWV proxies
    script_tags = soup.find_all("script")
    link_stylesheets = soup.find_all("link", rel=lambda v: v and "stylesheet" in v.lower())
    stylesheet_count = len(link_stylesheets)
    blocking_script_count = sum(1 for s in script_tags if is_blocking_script(s))
    size_mb = page_size_bytes / 1024.0 / 1024.0
    ttfb_ms = elapsed_ms

    # Mobile & usability
    viewport_tag = soup.find("meta", attrs={"name": "viewport"})
    mobile_friendly = bool(viewport_tag and "width" in (viewport_tag.get("content") or "").lower())

    # Security headers
    hsts = headers.get("Strict-Transport-Security")
    csp = headers.get("Content-Security-Policy")
    xfo = headers.get("X-Frame-Options")
    xcto = headers.get("X-Content-Type-Options")
    refpol = headers.get("Referrer-Policy")
    perm_pol = headers.get("Permissions-Policy")
    mixed_content = detect_mixed_content(soup, page_scheme)

    # robots/sitemap
    origin = f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}"
    robots_resp = safe_request(urljoin(origin, "/robots.txt"), "HEAD")
    sitemap_resp = safe_request(urljoin(origin, "/sitemap.xml"), "HEAD")
    has_robots = bool(robots_resp and robots_resp.status_code < 400)
    has_sitemap = bool(sitemap_resp and sitemap_resp.status_code < 400)

    # Crawl internal pages to expand metrics (redirects, 4xx/5xx, chains)
    crawled = crawl_internal(final_url, max_pages=deep_crawl_pages)
    total_crawled_pages = len(crawled)
    status_counts = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0, "none": 0}
    redirect_chains = 0
    slow_pages = 0
    large_pages = 0
    for item in crawled:
        s = item["status"]
        if s is None:
            status_counts["none"] += 1
        elif 200 <= s < 300:
            status_counts["2xx"] += 1
        elif 300 <= s < 400:
            status_counts["3xx"] += 1
        elif 400 <= s < 500:
            status_counts["4xx"] += 1
        elif 500 <= s < 600:
            status_counts["5xx"] += 1
        redirect_chains += (1 if item["redirects"] >= 2 else 0)
        slow_pages += (1 if item["ttfb_ms"] > 1500 else 0)
        large_pages += (1 if item["size_bytes"] > 1_000_000 else 0)

    # ----------------- Issues (60+ metrics heuristics) -----------------
    # SEO
    if not title_tag: errors.append({"name": "Missing <title>", "severity": "high",
                                     "suggestion": "Add a concise, keyword-rich title (50–60 chars)."})
    elif len(title_tag) < 10 or len(title_tag) > 65:
        warnings.append({"name": "Title length suboptimal", "severity": "medium",
                         "suggestion": "Keep titles ~50–60 characters."})

    if not meta_desc:
        warnings.append({"name": "Missing meta description", "severity": "medium",
                         "suggestion": "Add a compelling 120–160 character description."})
    elif len(meta_desc) < 50 or len(meta_desc) > 170:
        notices.append({"name": "Meta description length outside ideal range", "severity": "low",
                        "suggestion": "Keep descriptions ~120–160 characters."})

    if h1_count != 1:
        warnings.append({"name": f"H1 count is {h1_count}", "severity": "medium",
                         "suggestion": "Use exactly one H1 that matches the page’s main topic."})

    if not canonical_link:
        notices.append({"name": "Missing canonical link", "severity": "low",
                        "suggestion": "Add <link rel='canonical'> to prevent duplicate indexing."})

    if imgs_without_alt > 0:
        ratio = pct(imgs_without_alt, total_imgs)
        sev = "medium" if ratio > 20 else "low"
        (warnings if sev == "medium" else notices).append({
            "name": f"{imgs_without_alt} images missing alt", "severity": sev,
            "suggestion": "Provide descriptive alt text for all images."
        })

    if ld_json_count == 0:
        notices.append({"name": "No structured data (JSON-LD)", "severity": "low",
                        "suggestion": "Add relevant schema (Organization, Breadcrumb, Product, etc.)."})

    # Social meta
    if not og_meta:
        notices.append({"name": "Open Graph tags missing", "severity": "low",
                        "suggestion": "Add og:title, og:description, og:image for social sharing."})
    if not twitter_meta:
        notices.append({"name": "Twitter Card tags missing", "severity": "low",
                        "suggestion": "Add twitter:title, twitter:description, twitter:image."})

    # Crawlability & links
    if broken_internal > 0:
        errors.append({"name": f"Broken internal links: {broken_internal}", "severity": "high",
                       "suggestion": "Fix or remove broken internal links."})
    if broken_external > 0:
        warnings.append({"name": f"Broken external links: {broken_external}", "severity": "medium",
                         "suggestion": "Update or remove broken external links."})
    if status_counts["4xx"] > 0 or status_counts["5xx"] > 0:
        errors.append({"name": f"Error pages: 4xx={status_counts['4xx']}, 5xx={status_counts['5xx']}", "severity": "high",
                       "suggestion": "Resolve broken pages and server errors."})
    if redirect_chains > 0:
        warnings.append({"name": f"Redirect chains detected: {redirect_chains}", "severity": "medium",
                         "suggestion": "Simplify redirects to single hop."})

    # robots/sitemap
    if not has_robots:
        notices.append({"name": "robots.txt not found", "severity": "low", "suggestion": "Add robots.txt."})
    if not has_sitemap:
        notices.append({"name": "sitemap.xml not found", "severity": "low", "suggestion": "Add sitemap.xml and reference in robots.txt."})

    # Performance
    if size_mb > 2.0:
        errors.append({"name": f"Large homepage payload (~{size_mb:.2f} MB)", "severity": "high",
                       "suggestion": "Compress images (WebP/AVIF), minify/bundle assets, lazy-load media."})
    elif size_mb > 1.0:
        warnings.append({"name": f"Heavy homepage (~{size_mb:.2f} MB)", "severity": "medium",
                         "suggestion": "Optimize assets; enable compression; trim third-party scripts."})
    if ttfb_ms > 1500:
        errors.append({"name": f"Slow TTFB (~{ttfb_ms} ms)", "severity": "high",
                       "suggestion": "Add CDN/edge caching, optimize origin, use HTTP/2/3."})
    elif ttfb_ms > 800:
        warnings.append({"name": f"Elevated TTFB (~{ttfb_ms} ms)", "severity": "medium",
                         "suggestion": "Improve caching and server performance."})
    if blocking_script_count > 3:
        warnings.append({"name": f"Many render-blocking scripts ({blocking_script_count})", "severity": "medium",
                         "suggestion": "Add async/defer; split bundles; consider type='module'."})
    elif blocking_script_count > 0:
        notices.append({"name": f"Some blocking scripts ({blocking_script_count})", "severity": "low",
                        "suggestion": "Add async/defer to reduce blocking."})
    if stylesheet_count > 4:
        notices.append({"name": f"Many stylesheets ({stylesheet_count})", "severity": "low",
                        "suggestion": "Bundle/minify CSS; inline critical CSS."})
    if slow_pages > 0:
        warnings.append({"name": f"Slow internal pages: {slow_pages}", "severity": "medium",
                         "suggestion": "Investigate server-side bottlenecks and caching for slow pages."})
    if large_pages > 0:
        warnings.append({"name": f"Large internal pages: {large_pages}", "severity": "medium",
                         "suggestion": "Compress and optimize assets on heavy pages."})

    # Mobile & usability
    if not mobile_friendly:
        warnings.append({"name": "No responsive viewport meta", "severity": "medium",
                         "suggestion": "Add <meta name='viewport' content='width=device-width, initial-scale=1'>."})

    # Security
    if page_scheme != "https":
        errors.append({"name": "Homepage served over HTTP", "severity": "high",
                       "suggestion": "Redirect to HTTPS and install valid TLS."})
    if not hsts:
        warnings.append({"name": "Missing HSTS", "severity": "medium",
                         "suggestion": "Add Strict-Transport-Security header."})
    if not csp:
        warnings.append({"name": "Missing CSP", "severity": "medium",
                         "suggestion": "Add Content-Security-Policy to restrict sources & mitigate XSS."})
    if not xfo:
        notices.append({"name": "Missing X-Frame-Options", "severity": "low",
                        "suggestion": "Add X-Frame-Options or CSP frame-ancestors."})
    if not xcto:
        notices.append({"name": "Missing X-Content-Type-Options", "severity": "low",
                        "suggestion": "Add X-Content-Type-Options: nosniff."})
    if not refpol:
        notices.append({"name": "Missing Referrer-Policy", "severity": "low",
                        "suggestion": "Add Referrer-Policy."})
    if not perm_pol:
        notices.append({"name": "Missing Permissions-Policy", "severity": "low",
                        "suggestion": "Add Permissions-Policy."})
    if detect_mixed_content(soup, page_scheme):
        errors.append({"name": "Mixed content", "severity": "high",
                       "suggestion": "Ensure all resources load via HTTPS; fix http:// references."})

    # ----------------- Strict scoring -----------------
    # Start from 100 each category, deduct per issue (strict)
    seo_score = 100; perf_score = 100; a11y_score = 100; bp_score = 100; sec_score = 100

    # SEO penalties
    if not title_tag: seo_score -= 25
    if title_tag and (len(title_tag) < 10 or len(title_tag) > 65): seo_score -= 8
    if not meta_desc: seo_score -= 18
    if meta_desc and (len(meta_desc) < 50 or len(meta_desc) > 170): seo_score -= 6
    if h1_count != 1: seo_score -= 12
    if not canonical_link: seo_score -= 6
    if imgs_without_alt > 0 and pct(imgs_without_alt, total_imgs) > 20: seo_score -= 12
    if ld_json_count == 0: seo_score -= 6
    if broken_internal > 0: seo_score -= min(20, broken_internal * 2)

    # Performance penalties
    if size_mb > 2.0: perf_score -= 35
    elif size_mb > 1.0: perf_score -= 20
    if ttfb_ms > 1500: perf_score -= 35
    elif ttfb_ms > 800: perf_score -= 18
    if blocking_script_count > 3: perf_score -= 18
    elif blocking_script_count > 0: perf_score -= 10
    if stylesheet_count > 4: perf_score -= 6
    perf_score -= min(15, slow_pages * 2)
    perf_score -= min(15, large_pages * 2)

    # Accessibility penalties
    if not lang_attr: a11y_score -= 12
    if imgs_without_alt > 0:
        alt_ratio = pct(imgs_without_alt, total_imgs)
        if alt_ratio > 30: a11y_score -= 20
        elif alt_ratio > 10: a11y_score -= 12
        else: a11y_score -= 6

    # Best practices penalties
    if page_scheme != "https": bp_score -= 35
    if detect_mixed_content(soup, page_scheme): bp_score -= 15
    if any((s.get("type") == "text/javascript") for s in script_tags): bp_score -= 4
    if not has_sitemap: bp_score -= 6
    if redirect_chains > 0: bp_score -= min(12, redirect_chains * 2)

    # Security penalties
    if not hsts: sec_score -= 22
    if not csp: sec_score -= 18
    if not xfo: sec_score -= 10
    if not xcto: sec_score -= 10
    if not refpol: sec_score -= 6
    if not perm_pol: sec_score -= 6
    if mixed_content: sec_score -= 25

    # Overall site health score (weighted)
    site_health_score = round(
        0.26 * seo_score +
        0.28 * perf_score +
        0.14 * a11y_score +
        0.12 * bp_score +
        0.20 * sec_score
    )

    # CWV proxies
    largest_contentful_paint_ms = min(6000, int(1500 + size_mb * 1200 + blocking_script_count * 250))
    first_input_delay_ms = min(500, int(20 + blocking_script_count * 30))
    pass_rate = max(0, min(100, int(100 - (size_mb * 18 + blocking_script_count * 7 + (ttfb_ms / 120)))))

    # Compose issues list (top 10 by severity)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    top_issues = []
    for i in errors: i["severity"] = "high"; top_issues.append(i)
    for i in warnings: i["severity"] = "medium"; top_issues.append(i)
    for i in notices: i["severity"] = "low"; top_issues.append(i)
    top_issues.sort(key=lambda i: severity_order.get(i["severity"], 2))
    top_issues = top_issues[:10]

    # Summary metrics
    metrics_summary = {
        "total_errors": len(errors),
        "total_warnings": len(warnings),
        "total_notices": len(notices),
        "performance_score": max(0, perf_score),
        "seo_score": max(0, seo_score),
        "accessibility_score": max(0, a11y_score),
        "best_practices_score": max(0, bp_score),
        "security_score": max(0, sec_score),
        "pages_crawled": total_crawled_pages,
        "largest_contentful_paint_ms": largest_contentful_paint_ms,
        "first_input_delay_ms": first_input_delay_ms,
        "core_web_vitals_pass_rate_%": pass_rate,
        # Additional crawlability exposure:
        "http_2xx": status_counts["2xx"],
        "http_3xx": status_counts["3xx"],
        "http_4xx": status_counts["4xx"],
        "http_5xx": status_counts["5xx"],
        "broken_internal_links": broken_internal,
        "broken_external_links": broken_external,
        "redirect_chains": redirect_chains,
        "slow_pages_count": slow_pages,
        "large_pages_count": large_pages,
        "internal_links_count": internal_links,
        "external_links_count": external_links,
        "has_sitemap": int(has_sitemap),
        "has_robots": int(has_robots),
        "has_json_ld": int(ld_json_count > 0),
        "has_open_graph": int(bool(og_meta)),
        "has_twitter_card": int(bool(twitter_meta)),
        "mobile_friendly": int(mobile_friendly),
    }

    # Weaknesses list (high priority first)
    weaknesses = [i["name"] for i in errors] + [
        i["name"] for i in warnings if ("TTFB" in i["name"] or "render" in i["name"].lower() or "broken" in i["name"].lower())
    ]

    # Executive summary (≈200 words)
    exec_summary = (
        f"The audit of {final_url} reveals an overall site health score of {site_health_score} "
        f"with a grade of {grade_from_score(site_health_score)}. "
        f"Technical SEO indicators show {metrics_summary['broken_internal_links']} broken internal links and "
        f"{metrics_summary['http_4xx']} pages returning 4xx responses, which can hinder crawlability and indexing. "
        f"Performance analysis indicates a homepage payload of ~{size_mb:.2f} MB and TTFB around {ttfb_ms} ms; "
        f"render‑blocking scripts ({blocking_script_count}) and {stylesheet_count} stylesheets may delay interactivity. "
        f"Security headers require attention: HSTS={'present' if hsts else 'missing'}, CSP={'present' if csp else 'missing'}, "
        f"and mixed content is {'detected' if detect_mixed_content(soup, page_scheme) else 'not detected'}. "
        f"On‑page SEO can be strengthened with a precise title and meta description, canonical tags, alt attributes, "
        f"and structured data (JSON‑LD={'present' if ld_json_count else 'absent'}). "
        f"Mobile readiness is {'confirmed' if mobile_friendly else 'not confirmed'} via viewport meta. "
        f"To improve scores, fix broken links and error pages, compress and cache assets, add async/defer to scripts, "
        f"enable core security headers, and provide complete social metadata (Open Graph/Twitter). "
        f"With targeted optimization, {final_url} can improve Core Web Vitals, enhance crawlability, and strengthen "
        f"security posture while delivering a faster, more accessible experience."
    )

    audit = {
        "website": {"url": final_url},
        "site_health_score": site_health_score,
        "grade": grade_from_score(site_health_score),
        "competitors": [],  # future hook
        "top_issues": top_issues,
        "metrics_summary": metrics_summary,
        "recommendations": _default_recommendations(),
        "weaknesses": weaknesses,
        "finished_at": datetime.now().strftime("%b %d, %Y %H:%M"),
        "executive_summary": exec_summary,
    }
    return {"audit": audit, "previous_audit": None}


def _default_recommendations() -> dict:
    return {
        "total_errors": "Fix errors first; they block indexing or break UX.",
        "total_warnings": "Address warnings next; they impact performance and ranking.",
        "total_notices": "Optional improvements for incremental gains.",
        "performance_score": "Optimize images, enable compression, reduce render‑blocking scripts, and cache aggressively.",
        "seo_score": "Ensure unique titles, meta descriptions, H1, canonical tags, and structured data.",
        "accessibility_score": "Provide alt text, set language, and use landmarks/labels.",
        "best_practices_score": "Prefer HTTPS, avoid mixed content, and modern resource patterns.",
        "security_score": "Add HSTS, CSP, XFO, XCTO, Referrer/Permissions policies.",
        "pages_crawled": "Expand coverage via sitemaps and internal links.",
        "largest_contentful_paint_ms": "Inline critical CSS; preconnect; optimize hero assets.",
        "first_input_delay_ms": "Defer heavy JS; split bundles; reduce main-thread tasks.",
        "core_web_vitals_pass_rate_%": "Focus on LCP/CLS/INP; measure with RUM & lab tools.",
    }


# ------------------ PDF (Certified report) ------------------
def generate_certified_pdf(audit: dict) -> bytes:
    """
    Creates a branded PDF report using reportlab.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm
    from reportlab.lib import colors

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # Header with FF Tech logo
    logo_path = os.path.join("static", "fftech_logo.png")
    if os.path.isfile(logo_path):
        c.drawImage(logo_path, 2*cm, height - 3*cm, width=4*cm, height=1.5*cm, mask='auto')
    c.setFillColor(colors.HexColor("#6366F1"))
    c.setFont("Helvetica-Bold", 18)
    c.drawString(7*cm, height - 2.2*cm, "FF TECH · Certified Website Audit")

    # Website & grade
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 12)
    c.drawString(2*cm, height - 4*cm, f"Website: {audit['website']['url']}")
    c.drawString(2*cm, height - 4.7*cm, f"Generated: {audit['finished_at']}")

    c.setFont("Helvetica-Bold", 14)
    c.drawString(2*cm, height - 5.6*cm, f"Site Health Score: {audit['site_health_score']}%   Grade: {audit['grade']}")

    # Executive summary
    c.setFont("Helvetica-Bold", 13)
    c.drawString(2*cm, height - 7*cm, "Executive Summary:")
    c.setFont("Helvetica", 11)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Frame
    from reportlab.lib.enums import TA_LEFT
    style = ParagraphStyle(name="Body", fontName="Helvetica", fontSize=11, leading=14, alignment=TA_LEFT)
    frame = Frame(2*cm, height - 21*cm, width - 4*cm, 13*cm, showBoundary=0)
    story = [Paragraph(audit.get("executive_summary", ""), style)]
    frame.addFromList(story, c)

    # Certification footer
    c.setFont("Helvetica-Oblique", 10)
    c.setFillColor(colors.HexColor("#6366F1"))
    c.drawString(2*cm, 2*cm, "FF Tech · Certified Report · Valid for 30 days")
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


# ------------------ Auth helpers ------------------
def get_current_user(db: Session = Depends(get_db), token: str | None = None, request: Request | None = None) -> User:
    if token is None and request is not None:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_access_token(token)
    email = payload.get("sub")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ------------------ Startup ------------------
@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        admin = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if not admin:
            admin = User(email=ADMIN_EMAIL, password_hash=hash_password(ADMIN_PASSWORD), is_verified=True, is_admin=True)
            db.add(admin); db.commit()
            print(f"[INIT] Seeded admin {ADMIN_EMAIL}")
        # Load schedules into APScheduler
        scheduler.start()
        schedules = db.query(Schedule).filter(Schedule.enabled == True).all()
        for sch in schedules:
            cron = CronTrigger(hour=sch.hour_utc, minute=sch.minute_utc, timezone="UTC")
            scheduler.add_job(run_scheduled_audit, cron, args=[sch.id], id=f"sch-{sch.id}", replace_existing=True)
        print(f"[INIT] Loaded {len(schedules)} schedules")

@app.on_event("shutdown")
def shutdown():
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass


# ------------------ Scheduler job ------------------
def run_scheduled_audit(schedule_id: int):
    with SessionLocal() as db:
        sch = db.query(Schedule).filter(Schedule.id == schedule_id, Schedule.enabled == True).first()
        if not sch:
            return
        user = db.query(User).filter(User.id == sch.user_id).first()
        if not user or not user.is_verified:
            return
        data = audit_website(sch.url, deep_crawl_pages=20)
        audit = data["audit"]
        pdf_bytes = generate_certified_pdf(audit)

        # Persist audit under user
        a = Audit(
            user_id=user.id, url=audit["website"]["url"],
            site_health_score=audit["site_health_score"], grade=audit["grade"],
            metrics_summary_json=json.dumps(audit["metrics_summary"]),
            top_issues_json=json.dumps(audit["top_issues"]),
            executive_summary=audit.get("executive_summary", ""),
            finished_at=datetime.utcnow(),
        )
        db.add(a); db.commit()

        # Email report (daily or accumulated summary)
        subject = f"[FF Tech] {sch.report_type.title()} Audit Report — {audit['website']['url']}"
        if sch.report_type == "accumulated":
            # Compile trend for last 14 days
            recent = db.query(Audit).filter(Audit.user_id == user.id, Audit.url == sch.url)\
                .order_by(Audit.finished_at.desc()).limit(14).all()
            trend = ", ".join(str(x.site_health_score) for x in reversed(recent))
            body = (
                f"Hello,\n\nAttached is your accumulated audit report.\n"
                f"Website: {audit['website']['url']}\n"
                f"Latest Score: {audit['site_health_score']} (Grade {audit['grade']})\n"
                f"Trend (old→new): {trend}\n\nRegards,\nFF Tech"
            )
        else:
            body = (
                f"Hello,\n\nAttached is your daily audit snapshot.\n"
                f"Website: {audit['website']['url']}\n"
                f"Score: {audit['site_health_score']} (Grade {audit['grade']})\n\nRegards,\nFF Tech"
            )
        send_email(user.email, subject, body, attachments=[("FF-Tech-Certified-Audit.pdf", pdf_bytes)])


# ------------------ Routes: health & favicon ------------------
@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})

@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    p = os.path.join("static", "favicon.ico")
    if os.path.isfile(p):
        with open(p, "rb") as f:
            return Response(content=f.read(), media_type="image/x-icon")
    return Response(content=generate_favicon_bytes(), media_type="image/x-icon")


# ------------------ SSR (Open audit) ------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request, url: str | None = None, db: Session = Depends(get_db)) -> HTMLResponse:
    """
    Open audit mode — renders your existing index.html with audit data and saves audit (user_id=NULL).
    Use /?url=https://example.com
    """
    target_url = url or "https://example.com"
    data = audit_website(target_url, deep_crawl_pages=20)
    # Persist open audit
    a = Audit(
        user_id=None, url=data["audit"]["website"]["url"],
        site_health_score=data["audit"]["site_health_score"], grade=data["audit"]["grade"],
        metrics_summary_json=json.dumps(data["audit"]["metrics_summary"]),
        top_issues_json=json.dumps(data["audit"]["top_issues"]),
        executive_summary=data["audit"].get("executive_summary", ""),
        finished_at=datetime.utcnow(),
    )
    db.add(a); db.commit()

    context = {"request": request, **data}
    # Your template already uses: audit.*, previous_audit (None), charts, score, grade, etc.
    return templates.TemplateResponse("index.html", context)


# ------------------ JSON APIs ------------------
@app.get("/api/audit")
def api_audit(url: str, db: Session = Depends(get_db)) -> JSONResponse:
    """
    Open audit (no auth) — returns JSON and stores result (user_id=NULL).
    """
    data = audit_website(url, deep_crawl_pages=20)
    a = Audit(
        user_id=None, url=data["audit"]["website"]["url"],
        site_health_score=data["audit"]["site_health_score"], grade=data["audit"]["grade"],
        metrics_summary_json=json.dumps(data["audit"]["metrics_summary"]),
        top_issues_json=json.dumps(data["audit"]["top_issues"]),
        executive_summary=data["audit"].get("executive_summary", ""),
        finished_at=datetime.utcnow(),
    )
    db.add(a); db.commit()
    return JSONResponse(data)

@app.get("/api/audit-auth")
def api_audit_auth(url: str, request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    """
    Authenticated audit — requires Authorization: Bearer <token>.
    Saves audit under user's account and returns JSON.
    """
    user = get_current_user(db=db, request=request)
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Email not verified")
    data = audit_website(url, deep_crawl_pages=20)
    a = Audit(
        user_id=user.id, url=data["audit"]["website"]["url"],
        site_health_score=data["audit"]["site_health_score"], grade=data["audit"]["grade"],
        metrics_summary_json=json.dumps(data["audit"]["metrics_summary"]),
        top_issues_json=json.dumps(data["audit"]["top_issues"]),
        executive_summary=data["audit"].get("executive_summary", ""),
        finished_at=datetime.utcnow(),
    )
    db.add(a); db.commit()
    return JSONResponse(data)

@app.get("/api/audit/pdf")
def api_audit_pdf(url: str) -> StreamingResponse:
    """
    Generate on-demand certified PDF for a given URL (open mode).
    """
    data = audit_website(url, deep_crawl_pages=20)
    pdf_bytes = generate_certified_pdf(data["audit"])
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf",
                             headers={"Content-Disposition": 'attachment; filename="FF-Tech-Certified-Audit.pdf"'})


# ------------------ Auth (register, verify, login) ------------------
@app.post("/auth/register")
def register(email: str = Body(...), password: str = Body(...), timezone: str = Body("UTC"), db: Session = Depends(get_db)) -> JSONResponse:
    try:
        validate_email(email)
    except EmailNotValidError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=email, password_hash=hash_password(password), is_verified=False, is_admin=False, timezone=timezone)
    db.add(user); db.commit(); db.refresh(user)

    token = serializer.dumps({"email": email}, salt="verify-email")
    send_verification_email(email, token)
    return JSONResponse({"message": "Registered. Please check your email to verify."})

@app.get("/auth/verify")
def verify(token: str, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        data = serializer.loads(token, salt="verify-email", max_age=60*60*24)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail="Verification link expired")
    except BadSignature:
        raise HTTPException(status_code=400, detail="Invalid verification link")
    email = data.get("email")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_verified = True; db.commit()
    return JSONResponse({"message": "Email verified successfully. You may now log in."})

@app.post("/auth/login")
def login(email: str = Body(...), password: str = Body(...), db: Session = Depends(get_db)) -> JSONResponse:
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": user.email})
    return JSONResponse({"access_token": token, "token_type": "bearer", "is_admin": user.is_admin, "is_verified": user.is_verified})


# ------------------ Scheduling ------------------
@app.post("/schedule/set")
def schedule_set(
    url: str = Body(...),
    hour_local: int = Body(..., ge=0, le=23),
    minute_local: int = Body(..., ge=0, le=59),
    report_type: str = Body("daily"),
    request: Request = None,
    db: Session = Depends(get_db)
) -> JSONResponse:
    """
    Set a daily schedule at the user's local time (timezone saved in profile).
    Converts to UTC for APScheduler.
    """
    user = get_current_user(db=db, request=request)
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Email not verified")

    # Convert local (user.timezone) to UTC — using Python's zoneinfo
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(user.timezone)
    except Exception:
        tz = ZoneInfo("UTC")

    now_local = datetime.now(tz)
    target_local = now_local.replace(hour=hour_local, minute=minute_local, second=0, microsecond=0)
    # If time already passed today, schedule tomorrow
    if target_local <= now_local:
        target_local += timedelta(days=1)
    target_utc = target_local.astimezone(ZoneInfo("UTC"))

    sch = Schedule(user_id=user.id, url=normalize_url(url),
                   hour_utc=target_utc.hour, minute_utc=target_utc.minute,
                   enabled=True, report_type=report_type)
    db.add(sch); db.commit(); db.refresh(sch)

    # Add job to scheduler
    cron = CronTrigger(hour=sch.hour_utc, minute=sch.minute_utc, timezone="UTC")
    scheduler.add_job(run_scheduled_audit, cron, args=[sch.id], id=f"sch-{sch.id}", replace_existing=True)

    return JSONResponse({"message": "Schedule set", "schedule_id": sch.id, "utc_time": f"{sch.hour_utc:02d}:{sch.minute_utc:02d}"})


@app.post("/schedule/disable")
def schedule_disable(schedule_id: int = Body(...), request: Request = None, db: Session = Depends(get_db)) -> JSONResponse:
    user = get_current_user(db=db, request=request)
    sch = db.query(Schedule).filter(Schedule.id == schedule_id, Schedule.user_id == user.id).first()
    if not sch:
        raise HTTPException(status_code=404, detail="Schedule not found")
    sch.enabled = False; db.commit()
    try:
        scheduler.remove_job(f"sch-{schedule_id}")
    except Exception:
        pass
    return JSONResponse({"message": "Schedule disabled"})


# ------------------ Admin ------------------
@app.get("/admin/audits")
def admin_audits(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    admin = get_current_user(db=db, request=request)
    if not admin.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")
    rows = db.query(Audit).order_by(Audit.finished_at.desc()).limit(500).all()
    return JSONResponse({"audits": [
        {"id": a.id, "user_id": a.user_id, "url": a.url, "score": a.site_health_score, "grade": a.grade,
         "finished_at": a.finished_at.isoformat()}
        for a in rows
    ]})

@app.get("/admin/users")
def admin_users(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    admin = get_current_user(db=db, request=request)
    if not admin.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")
    rows = db.query(User).order_by(User.created_at.desc()).limit(500).all()
    return JSONResponse({"users": [
        {"id": u.id, "email": u.email, "verified": u.is_verified, "admin": u.is_admin, "timezone": u.timezone,
         "created_at": u.created_at.isoformat()}
        for u in rows
    ]})

@app.get("/admin/schedules")
def admin_schedules(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    admin = get_current_user(db=db, request=request)
    if not admin.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")
    rows = db.query(Schedule).order_by(Schedule.created_at.desc()).limit(500).all()
    return JSONResponse({"schedules": [
        {"id": s.id, "user_id": s.user_id, "url": s.url, "utc": f"{s.hour_utc:02d}:{s.minute_utc:02d}", "enabled": s.enabled,
         "report_type": s.report_type, "created_at": s.created_at.isoformat()}
        for s in rows
    ]})
