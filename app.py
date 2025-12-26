
# app.py
# FF Tech Elite | Premium Audit Engine — FastAPI backend
# Key features:
# - Serves your HTML at "/" (templates/index.html)
# - AJAX endpoints: /api/audit, /api/history, /api/audit/pdf, /run-audit
# - Email magic-link (optional): /auth/send-link -> /auth/verify
# - Admin login: /auth/admin-login (JWT) and protected admin APIs
# - DB: PostgreSQL (Railway) via SQLAlchemy; SQLite fallback locally
# - Audit engine: 60+ metrics with strict scoring
# - Certified PDF: 5 pages; per-audit download limit = 3

import os
import io
import json
import base64
import smtplib
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from email_validator import validate_email, EmailNotValidError
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from fastapi import FastAPI, Request, Depends, HTTPException, Body, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session

from passlib.context import CryptContext
import jwt

# Optional: Pillow for fallback favicon generation
try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# ------------------ Config ------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./db.sqlite3")
SECRET_KEY    = os.getenv("SECRET_KEY", "change-this-in-production")
ALGORITHM     = "HS256"
PUBLIC_URL    = os.getenv("PUBLIC_URL", "http://localhost:8000")

# Admin credentials (seeded on startup)
ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL", "roy.jamshaid@gmail.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Jamshaid,1981")

# SMTP (optional)
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@fftech.example")

serializer  = URLSafeTimedSerializer(SECRET_KEY)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine       = create_engine(DATABASE_URL, echo=False, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
Base         = declarative_base()

# ------------------ App ------------------
app = FastAPI()

# Static serving (logo, favicon)
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Template (your HTML lives in templates/index.html)
templates = Jinja2Templates(directory="templates")

# CORS so the page can fetch the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your domain in production
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ------------------ DB Models ------------------
class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True)
    email         = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_verified   = Column(Boolean, default=False)
    is_admin      = Column(Boolean, default=False)
    created_at    = Column(DateTime, default=datetime.utcnow)
    audits        = relationship("Audit", back_populates="user", cascade="all,delete")


class Audit(Base):
    __tablename__ = "audits"
    id                   = Column(Integer, primary_key=True)
    user_id              = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL for open audits
    url                  = Column(String(2048), nullable=False)
    site_health_score    = Column(Integer, default=0)
    grade                = Column(String(4), default="F")
    metrics_summary_json = Column(Text, default="{}")
    top_issues_json      = Column(Text, default="[]")
    executive_summary    = Column(Text, default="")
    finished_at          = Column(DateTime, default=datetime.utcnow)
    user                 = relationship("User", back_populates="audits")


class PdfDownload(Base):
    __tablename__ = "pdf_downloads"
    id             = Column(Integer, primary_key=True)
    audit_id       = Column(Integer, ForeignKey("audits.id"), nullable=False)
    downloads      = Column(Integer, default=0)
    allowed        = Column(Integer, default=3)  # limit to 3 times
    last_download  = Column(DateTime, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)


class MagicToken(Base):
    __tablename__ = "magic_tokens"
    id        = Column(Integer, primary_key=True)
    email     = Column(String(255), index=True)
    token     = Column(String(512), unique=True)
    created_at= Column(DateTime, default=datetime.utcnow)
    used      = Column(Boolean, default=False)


# ------------------ Auth helpers ------------------
def create_access_token(data: dict, expires_minutes: int = 24*60) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ------------------ Startup: create tables + seed admin ------------------
@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        admin = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if not admin:
            admin = User(
                email=ADMIN_EMAIL,
                password_hash=pwd_context.hash(ADMIN_PASSWORD),
                is_verified=True,
                is_admin=True,
            )
            db.add(admin)
            db.commit()
            print(f"[INIT] Seeded admin {ADMIN_EMAIL}")
        else:
            print(f"[INIT] Admin {ADMIN_EMAIL} exists")


# ------------------ Email ------------------
def send_email(to_email: str, subject: str, body: str):
    if SMTP_HOST and SMTP_USER and SMTP_PASS:
        try:
            msg = f"From: {SMTP_FROM}\r\nTo: {to_email}\r\nSubject: {subject}\r\n\r\n{body}"
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_FROM, [to_email], msg)
            print(f"[EMAIL] Sent to {to_email}")
        except Exception as e:
            print(f"[EMAIL] Failed: {e}\nSubject: {subject}\n{body}")
    else:
        print(f"[EMAIL] SMTP not configured.\nTo: {to_email}\nSubject: {subject}\n{body}")


# ------------------ Utilities ------------------
def grade_from_score(score: int) -> str:
    if score >= 95: return "A+"
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"


def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw: return raw
    parsed = urlparse(raw)
    if not parsed.scheme:
        raw = "https://" + raw
    return raw


def safe_request(url: str, method: str = "GET", **kwargs) -> requests.Response | None:
    try:
        kwargs.setdefault("timeout", (8, 16))
        kwargs.setdefault("allow_redirects", True)
        kwargs.setdefault("headers", {"User-Agent": "FFTech-Elite-AuditBot/1.0 (+https://fftech.example)"})
        return requests.request(method.upper(), url, **kwargs)
    except Exception:
        return None


def detect_mixed_content(soup: BeautifulSoup, scheme: str) -> bool:
    if scheme != "https": return False
    for tag in soup.find_all(["img","script","link","iframe","video","audio","source"]):
        for attr in ["src","href","data","poster"]:
            val = tag.get(attr)
            if isinstance(val, str) and val.startswith("http://"):
                return True
    return False


def is_blocking_script(tag) -> bool:
    if tag.name != "script": return False
    if tag.get("type") == "module": return False
    return not (tag.get("async") or tag.get("defer"))


def pct(n: int, d: int) -> float:
    return (n / d * 100.0) if d else 0.0


# ------------------ Crawl ------------------
def crawl_internal(seed_url: str, max_pages: int = 20) -> list[dict]:
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
        try:
            soup = BeautifulSoup(resp.text or "", "html.parser")
            for a in soup.find_all("a"):
                href = a.get("href") or ""
                if not href: continue
                abs_url = urljoin(final, href)
                parsed = urlparse(abs_url)
                if parsed.netloc == host and parsed.scheme in ("http","https"):
                    if abs_url not in visited and abs_url not in queue:
                        queue.append(abs_url)
                if len(queue) > max_pages*3:
                    queue = queue[:max_pages*3]
        except Exception:
            pass
    return results


# ------------------ Hreflang ------------------
VALID_LANGS = {"en","ar","de","es","fr","it","ja","ko","nl","pt","ru","sv","tr","zh","zh-cn","zh-hk","zh-tw","hi","ur","fa","pl","cs","da","el","fi","he","hu","id","ms","no","ro","sk","th","uk","vi"}
def validate_hreflang(soup: BeautifulSoup) -> dict:
    errors = []; notices = []
    tags = soup.find_all("link", attrs={"rel":"alternate", "hreflang": True})
    for t in tags:
        code = (t.get("hreflang") or "").lower().strip()
        if code == "x-default": continue
        ok = code in VALID_LANGS or (len(code.split("-"))==2 and code.split("-")[0] in VALID_LANGS)
        if not ok:
            errors.append({"name": f"Invalid hreflang code: {code}", "severity":"high",
                           "suggestion":"Use valid ISO codes (e.g., en, en-GB, fr-FR)."})
    if not tags:
        notices.append({"name":"No hreflang tags", "severity":"low",
                        "suggestion":"Add hreflang for multi-language sites."})
    return {"errors": errors, "notices": notices, "count": len(tags)}


# ------------------ Audit Engine ------------------
def audit_website(url: str, deep_crawl_pages: int = 15) -> dict:
    url = normalize_url(url)
    resp = safe_request(url, "GET")
    errors: list[dict] = []; warnings: list[dict] = []; notices: list[dict] = []

    status_code = resp.status_code if resp else None
    final_url   = resp.url if resp else url
    headers     = dict(resp.headers) if resp else {}
    elapsed_ms  = int(resp.elapsed.total_seconds() * 1000) if resp else 0
    html        = resp.text if (resp and resp.text) else ""
    page_size_bytes = len(resp.content) if resp else 0
    scheme      = urlparse(final_url).scheme or "https"

    # Early failure
    if not resp or (status_code and status_code >= 400):
        errors.append({"name":"Homepage unreachable or error status","severity":"high","suggestion":"Fix DNS/TLS/server errors; homepage must return 200."})
        ms = {
            "total_errors": len(errors), "total_warnings": 0, "total_notices": 0,
            "performance_score": 0, "seo_score": 0, "accessibility_score": 0, "best_practices_score": 0, "security_score": 0,
            "pages_crawled": 0, "largest_contentful_paint_ms": 0, "first_input_delay_ms": 0, "core_web_vitals_pass_rate_%": 0,
        }
        return {
            "audit": {
                "website":{"url":url}, "site_health_score":0, "grade":grade_from_score(0),
                "top_issues": errors, "metrics_summary": ms, "recommendations": _default_recommendations(),
                "weaknesses":[e["name"] for e in errors],
                "finished_at": datetime.now().strftime("%b %d, %Y %H:%M"),
                "executive_summary":"Homepage is unreachable; fix availability, server configuration, DNS and TLS.",
            },
            "previous_audit": None
        }

    soup = BeautifulSoup(html, "html.parser")

    # SEO & On-page
    title_tag = soup.title.string.strip() if soup.title and soup.title.string else ""
    meta_desc_tag = soup.find("meta", attrs={"name":"description"})
    meta_desc = (meta_desc_tag.get("content") or "").strip() if meta_desc_tag else ""
    h1_tags = soup.find_all("h1"); h1_count = len(h1_tags)
    canonical_link = soup.find("link", rel=lambda v: v and "canonical" in v.lower())
    lang_attr = soup.html.get("lang") if soup.html else None
    robots_meta_tag = soup.find("meta", attrs={"name":"robots"})
    robots_meta = (robots_meta_tag.get("content") or "").lower().strip() if robots_meta_tag else ""
    img_tags = soup.find_all("img"); total_imgs = len(img_tags)
    imgs_without_alt = len([i for i in img_tags if not (i.get("alt") and i.get("alt").strip())])
    ld_json_count = len(soup.find_all("script", attrs={"type":"application/ld+json"}))
    og_meta = soup.find("meta", property=lambda v: v and v.startswith("og:"))
    twitter_meta = soup.find("meta", attrs={"name": lambda v: v and v.startswith("twitter:")})

    # Links
    a_tags = soup.find_all("a"); host = urlparse(final_url).netloc
    internal_links = external_links = broken_internal = broken_external = 0
    for a in a_tags:
        href = a.get("href") or ""
        if not href: continue
        abs_url = urljoin(final_url, href)
        netloc  = urlparse(abs_url).netloc
        if href.startswith("#") or netloc == host: internal_links += 1
        else: external_links += 1
        head = safe_request(abs_url, "HEAD")
        if not head or (head.status_code and head.status_code >= 400):
            if netloc == host or href.startswith("#"): broken_internal += 1
            else: broken_external += 1

    # Performance heuristics
    script_tags = soup.find_all("script")
    link_stylesheets = soup.find_all("link", rel=lambda v: v and "stylesheet" in v.lower())
    stylesheet_count = len(link_stylesheets)
    blocking_script_count = sum(1 for s in script_tags if is_blocking_script(s))
    size_mb = page_size_bytes / 1024.0 / 1024.0
    ttfb_ms = elapsed_ms

    # Mobile
    viewport_tag = soup.find("meta", attrs={"name":"viewport"})
    mobile_friendly = bool(viewport_tag and "width" in (viewport_tag.get("content") or "").lower())

    # Security headers
    hsts = headers.get("Strict-Transport-Security")
    csp  = headers.get("Content-Security-Policy")
    xfo  = headers.get("X-Frame-Options")
    xcto = headers.get("X-Content-Type-Options")
    refpol = headers.get("Referrer-Policy")
    perm_pol = headers.get("Permissions-Policy")
    mixed_content = detect_mixed_content(soup, scheme)

    # robots/sitemap
    origin = f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}"
    robots_resp  = safe_request(urljoin(origin, "/robots.txt"), "HEAD")
    sitemap_resp = safe_request(urljoin(origin, "/sitemap.xml"), "HEAD")
    has_robots  = bool(robots_resp and robots_resp.status_code < 400)
    has_sitemap = bool(sitemap_resp and sitemap_resp.status_code < 400)

    # hreflang
    hreflang_check = validate_hreflang(soup)
    errors   += hreflang_check["errors"]
    notices  += hreflang_check["notices"]

    # Deep crawl
    crawled = crawl_internal(final_url, max_pages=deep_crawl_pages)
    total_crawled_pages = len(crawled)
    status_counts = {"2xx":0,"3xx":0,"4xx":0,"5xx":0,"none":0}
    redirect_chains = slow_pages = large_pages = 0
    for item in crawled:
        s = item["status"]
        if s is None: status_counts["none"] += 1
        elif 200 <= s < 300: status_counts["2xx"] += 1
        elif 300 <= s < 400: status_counts["3xx"] += 1
        elif 400 <= s < 500: status_counts["4xx"] += 1
        elif 500 <= s < 600: status_counts["5xx"] += 1
        redirect_chains += (1 if item["redirects"] >= 2 else 0)
        slow_pages += (1 if item["ttfb_ms"] > 1500 else 0)
        large_pages += (1 if item["size_bytes"] > 1_000_000 else 0)

    # Issues
    if not title_tag:
        errors.append({"name":"Missing <title>","severity":"high","suggestion":"Add a concise, keyword-rich title (50–60 chars)."})
    elif len(title_tag) < 10 or len(title_tag) > 65:
        warnings.append({"name":"Title length suboptimal","severity":"medium","suggestion":"Keep titles ~50–60 characters."})
    if not meta_desc:
        warnings.append({"name":"Missing meta description","severity":"medium","suggestion":"Add 120–160 character description."})
    elif len(meta_desc) < 50 or len(meta_desc) > 170:
        notices.append({"name":"Meta description outside ideal range","severity":"low","suggestion":"Keep 120–160 chars."})
    if h1_count != 1:
        warnings.append({"name":f"H1 count is {h1_count}","severity":"medium","suggestion":"Use exactly one H1."})
    if not canonical_link:
        notices.append({"name":"Missing canonical link","severity":"low","suggestion":"Add <link rel='canonical'>."})
    if imgs_without_alt > 0:
        ratio = pct(imgs_without_alt, total_imgs)
        sev = "medium" if ratio > 20 else "low"
        (warnings if sev=="medium" else notices).append({"name":f"{imgs_without_alt} images missing alt","severity":sev,"suggestion":"Add descriptive alt attributes."})
    if ld_json_count == 0:
        notices.append({"name":"No JSON‑LD structured data","severity":"low","suggestion":"Add relevant schema.org."})
    if not og_meta:
        notices.append({"name":"Open Graph tags missing","severity":"low","suggestion":"Add og:title/description/image."})
    if not twitter_meta:
        notices.append({"name":"Twitter Card tags missing","severity":"low","suggestion":"Add twitter:title/description/image."})
    if broken_internal > 0:
        errors.append({"name":f"Broken internal links: {broken_internal}","severity":"high","suggestion":"Fix or remove broken internal links."})
    if broken_external > 0:
        warnings.append({"name":f"Broken external links: {broken_external}","severity":"medium","suggestion":"Update or remove broken external links."})
    if status_counts["4xx"] > 0 or status_counts["5xx"] > 0:
        errors.append({"name":f"Error pages (4xx={status_counts['4xx']}, 5xx={status_counts['5xx']})","severity":"high","suggestion":"Resolve broken pages and server errors."})
    if redirect_chains > 0:
        warnings.append({"name":f"Redirect chains: {redirect_chains}","severity":"medium","suggestion":"Simplify redirects to single hop."})
    if not has_robots:
        notices.append({"name":"robots.txt missing","severity":"low","suggestion":"Add robots.txt."})
    if not has_sitemap:
        notices.append({"name":"sitemap.xml missing","severity":"low","suggestion":"Add sitemap.xml and reference in robots.txt."})
    if size_mb > 2.0:
        errors.append({"name":f"Large homepage (~{size_mb:.2f} MB)","severity":"high","suggestion":"Compress images (WebP/AVIF), minify assets, lazy‑load media."})
    elif size_mb > 1.0:
        warnings.append({"name":f"Heavy homepage (~{size_mb:.2f} MB)","severity":"medium","suggestion":"Optimize assets; enable compression; trim third‑party scripts."})
    if ttfb_ms > 1500:
        errors.append({"name":f"Slow TTFB (~{ttfb_ms} ms)","severity":"high","suggestion":"Add CDN/edge cache; optimize origin; enable HTTP/2/3."})
    elif ttfb_ms > 800:
        warnings.append({"name":f"Elevated TTFB (~{ttfb_ms} ms)","severity":"medium","suggestion":"Improve caching and server performance."})
    if blocking_script_count > 3:
        warnings.append({"name":f"Many render‑blocking scripts ({blocking_script_count})","severity":"medium","suggestion":"Add async/defer; split bundles; use type='module'."})
    elif blocking_script_count > 0:
        notices.append({"name":f"Some blocking scripts ({blocking_script_count})","severity":"low","suggestion":"Add async/defer."})
    if stylesheet_count > 4:
        notices.append({"name":f"Many stylesheets ({stylesheet_count})","severity":"low","suggestion":"Bundle/minify CSS; inline critical CSS."})
    if not mobile_friendly:
        warnings.append({"name":"No responsive viewport meta","severity":"medium","suggestion":"Add <meta name='viewport' content='width=device-width, initial-scale=1'>."})
    if scheme != "https":
        errors.append({"name":"Homepage over HTTP","severity":"high","suggestion":"Force HTTPS with valid TLS."})
    if not hsts:
        warnings.append({"name":"Missing HSTS","severity":"medium","suggestion":"Add Strict‑Transport‑Security header."})
    if not csp:
        warnings.append({"name":"Missing CSP","severity":"medium","suggestion":"Add Content‑Security‑Policy to restrict sources."})
    if not xfo:
        notices.append({"name":"Missing X‑Frame‑Options","severity":"low","suggestion":"Add X‑Frame‑Options or CSP frame‑ancestors."})
    if not xcto:
        notices.append({"name":"Missing X‑Content‑Type‑Options","severity":"low","suggestion":"Add X‑Content‑Type‑Options: nosniff."})
    if not refpol:
        notices.append({"name":"Missing Referrer‑Policy","severity":"low","suggestion":"Add Referrer‑Policy."})
    if not perm_pol:
        notices.append({"name":"Missing Permissions‑Policy","severity":"low","suggestion":"Add Permissions‑Policy."})
    if detect_mixed_content(soup, scheme):
        errors.append({"name":"Mixed content","severity":"high","suggestion":"Serve all resources via HTTPS; fix http:// references."})

    # Strict scoring
    seo_score = 100; perf_score = 100; a11y_score = 100; bp_score = 100; sec_score = 100
    if not title_tag: seo_score -= 25
    if title_tag and (len(title_tag) < 10 or len(title_tag) > 65): seo_score -= 8
    if not meta_desc: seo_score -= 18
    if meta_desc and (len(meta_desc) < 50 or len(meta_desc) > 170): seo_score -= 6
    if h1_count != 1: seo_score -= 12
    if not canonical_link: seo_score -= 6
    if imgs_without_alt > 0 and pct(imgs_without_alt, total_imgs) > 20: seo_score -= 12
    if ld_json_count == 0: seo_score -= 6
    if broken_internal > 0: seo_score -= min(20, broken_internal * 2)

    if size_mb > 2.0: perf_score -= 35
    elif size_mb > 1.0: perf_score -= 20
    if ttfb_ms > 1500: perf_score -= 35
    elif ttfb_ms > 800: perf_score -= 18
    if blocking_script_count > 3: perf_score -= 18
    elif blocking_script_count > 0: perf_score -= 10
    if stylesheet_count > 4: perf_score -= 6
    perf_score -= min(15, slow_pages * 2)
    perf_score -= min(15, large_pages * 2)

    if not lang_attr: a11y_score -= 12
    if imgs_without_alt > 0:
        alt_ratio = pct(imgs_without_alt, total_imgs)
        if alt_ratio > 30: a11y_score -= 20
        elif alt_ratio > 10: a11y_score -= 12
        else: a11y_score -= 6

    if scheme != "https": bp_score -= 35
    if detect_mixed_content(soup, scheme): bp_score -= 15
    if any((s.get("type") == "text/javascript") for s in script_tags): bp_score -= 4
    if not has_sitemap: bp_score -= 6
    if redirect_chains > 0: bp_score -= min(12, redirect_chains * 2)

    if not hsts: sec_score -= 22
    if not csp: sec_score -= 18
    if not xfo: sec_score -= 10
    if not xcto: sec_score -= 10
    if not refpol: sec_score -= 6
    if not perm_pol: sec_score -= 6
    if mixed_content: sec_score -= 25

    site_health_score = round(
        0.26 * seo_score +
        0.28 * perf_score +
        0.14 * a11y_score +
        0.12 * bp_score +
        0.20 * sec_score
    )

    # CWV proxies
    largest_contentful_paint_ms = min(6000, int(1500 + size_mb*1200 + blocking_script_count*250))
    first_input_delay_ms        = min(500, int(20 + blocking_script_count*30))
    pass_rate                   = max(0, min(100, int(100 - (size_mb*18 + blocking_script_count*7 + (ttfb_ms/120)))))

    # Top Issues
    severity_order = {"high":0,"medium":1,"low":2}
    top_issues = []
    for i in errors:   i["severity"]="high";   top_issues.append(i)
    for i in warnings: i["severity"]="medium"; top_issues.append(i)
    for i in notices:  i["severity"]="low";    top_issues.append(i)
    top_issues.sort(key=lambda i: severity_order.get(i["severity"], 2))
    top_issues = top_issues[:10]

    metrics_summary = {
        "total_errors": len(errors), "total_warnings": len(warnings), "total_notices": len(notices),
        "performance_score": max(0, perf_score), "seo_score": max(0, seo_score),
        "accessibility_score": max(0, a11y_score), "best_practices_score": max(0, bp_score),
        "security_score": max(0, sec_score),
        "pages_crawled": total_crawled_pages,
        "largest_contentful_paint_ms": largest_contentful_paint_ms,
        "first_input_delay_ms": first_input_delay_ms,
        "core_web_vitals_pass_rate_%": pass_rate,
        "http_2xx": status_counts["2xx"], "http_3xx": status_counts["3xx"], "http_4xx": status_counts["4xx"], "http_5xx": status_counts["5xx"],
        "broken_internal_links": broken_internal, "broken_external_links": broken_external,
        "redirect_chains": redirect_chains, "slow_pages_count": slow_pages, "large_pages_count": large_pages,
        "internal_links_count": internal_links, "external_links_count": external_links,
        "has_sitemap": int(has_sitemap), "has_robots": int(has_robots),
        "has_json_ld": int(ld_json_count > 0), "has_open_graph": int(bool(og_meta)),
        "has_twitter_card": int(bool(twitter_meta)), "mobile_friendly": int(mobile_friendly),
        "hreflang_count": hreflang_check["count"],
    }

    weaknesses = [i["name"] for i in errors] + [
        i["name"] for i in warnings if ("TTFB" in i["name"] or "render" in i["name"].lower() or "broken" in i["name"].lower())
    ]

    exec_summary = (
        f"The audit of {final_url} yields a site health score of {site_health_score} "
        f"and grade {grade_from_score(site_health_score)}. "
        f"Crawlability shows {metrics_summary['broken_internal_links']} broken internal links and {metrics_summary['http_4xx']} pages with 4xx status. "
        f"Performance indicates a payload of ~{size_mb:.2f} MB and TTFB ~{ttfb_ms} ms, with {blocking_script_count} render‑blocking scripts and "
        f"{stylesheet_count} stylesheets affecting delivery. Security headers such as HSTS and CSP are "
        f"{'present' if (headers.get('Strict-Transport-Security') and headers.get('Content-Security-Policy')) else 'not fully implemented'}, "
        f"and mixed content is {'detected' if mixed_content else 'not detected'}. "
        f"On‑page fundamentals (title, meta, canonical, alt, JSON‑LD, social metadata) can strengthen SEO. "
        f"Mobile readiness is {'confirmed' if mobile_friendly else 'not confirmed'}. "
        f"Recommended actions: fix broken links and error pages, compress and cache assets, add async/defer to scripts, enable essential security headers, "
        f"and provide complete structured and social metadata to improve rankings, speed, and trust."
    )

    audit = {
        "website": {"url": final_url},
        "site_health_score": site_health_score,
        "grade": grade_from_score(site_health_score),
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


# ------------------ PDF (5 pages) ------------------
def generate_certified_pdf_5pages(audit: dict) -> bytes:
    """
    Generates a 5-page Certified PDF report:
    P1: Cover (logo, website, score, grade)
    P2: Executive Summary
    P3: Metrics Summary (key metrics)
    P4: Top Issues (table)
    P5: Recommendations & Weak Areas
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle, Paragraph, Frame
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT

    buf = io.BytesIO()
    c   = canvas.Canvas(buf, pagesize=A4)
    W, H= A4

    # --- PAGE 1: Cover ---
    logo_path = os.path.join("static", "fftech_logo.png")
    if os.path.isfile(logo_path):
        c.drawImage(logo_path, 2*cm, H - 3*cm, width=4*cm, height=1.5*cm, mask='auto')
    c.setFillColor(colors.HexColor("#6366F1")); c.setFont("Helvetica-Bold", 22)
    c.drawString(7*cm, H - 2.2*cm, "FF Tech Elite · Certified Audit")
    c.setFillColor(colors.black); c.setFont("Helvetica", 14)
    c.drawString(2*cm, H - 4*cm, f"Website: {audit['website']['url']}")
    c.drawString(2*cm, H - 4.8*cm, f"Generated: {audit['finished_at']}")
    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(colors.HexColor("#10b981"))
    c.drawString(2*cm, H - 6.2*cm, f"Site Health Score: {audit['site_health_score']}%")
    c.setFillColor(colors.HexColor("#f43f5e"))
    c.drawString(2*cm, H - 7.4*cm, f"Grade: {audit['grade']}")
    c.setFillColor(colors.HexColor("#6366F1")); c.setFont("Helvetica-Oblique", 12)
    c.drawString(2*cm, 2*cm, "FF Tech Elite · Certified Report · Valid for 30 days")
    c.showPage()

    # --- PAGE 2: Executive Summary ---
    style = ParagraphStyle(name="Body", fontName="Helvetica", fontSize=12, leading=16, alignment=TA_LEFT)
    frame = Frame(2*cm, 3*cm, W - 4*cm, H - 6*cm, showBoundary=0)
    title_style = ParagraphStyle(name="Title", fontName="Helvetica-Bold", fontSize=16, textColor=colors.HexColor("#6366F1"))
    story = [Paragraph("Executive Summary", title_style), Paragraph(audit.get("executive_summary", ""), style)]
    frame.addFromList(story, c)
    c.showPage()

    # --- PAGE 3: Metrics Summary ---
    c.setFont("Helvetica-Bold", 16); c.setFillColor(colors.HexColor("#6366F1"))
    c.drawString(2*cm, H - 3*cm, "Metrics Summary")
    ms = audit["metrics_summary"]
    rows = [
        ["Metric", "Value"],
        ["SEO Score",           ms["seo_score"]],
        ["Performance Score",   ms["performance_score"]],
        ["Security Score",      ms["security_score"]],
        ["Accessibility Score", ms["accessibility_score"]],
        ["Best Practices",      ms["best_practices_score"]],
        ["Pages Crawled",       ms["pages_crawled"]],
        ["Errors (4xx)",        ms["http_4xx"]],
        ["Errors (5xx)",        ms["http_5xx"]],
        ["Broken Internal Links", ms["broken_internal_links"]],
        ["Broken External Links", ms["broken_external_links"]],
        ["Redirect Chains",       ms["redirect_chains"]],
        ["LCP (ms)",              ms["largest_contentful_paint_ms"]],
        ["FID proxy (ms)",        ms["first_input_delay_ms"]],
        ["CWV Pass Rate (%)",     ms["core_web_vitals_pass_rate_%"]],
        ["Mobile Friendly",       "Yes" if ms["mobile_friendly"] else "No"],
        ["Sitemap",               "Yes" if ms["has_sitemap"] else "No"],
        ["robots.txt",            "Yes" if ms["has_robots"] else "No"],
    ]
    table = Table(rows, colWidths=[8*cm, 8*cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#6366F1")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,0), 12),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.grey),
        ("ALIGN",      (0,0), (-1,-1), "LEFT"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.lightgrey])
    ]))
    table.wrapOn(c, W, H)
    table.drawOn(c, 2*cm, H - 23*cm)
    c.showPage()

    # --- PAGE 4: Top Issues ---
    c.setFont("Helvetica-Bold", 16); c.setFillColor(colors.HexColor("#f43f5e"))
    c.drawString(2*cm, H - 3*cm, "Top Issues")
    issues = audit["top_issues"]
    issue_rows = [["Issue", "Severity", "Suggestion"]]
    for i in issues:
        issue_rows.append([i["name"], i["severity"].capitalize(), i["suggestion"]])
    table2 = Table(issue_rows, colWidths=[7*cm, 3*cm, 6*cm])
    table2.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f43f5e")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,0), 12),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.grey),
        ("ALIGN",      (0,0), (-1,-1), "LEFT"),
    ]))
    table2.wrapOn(c, W, H)
    table2.drawOn(c, 2*cm, H - 25*cm)
    c.showPage()

    # --- PAGE 5: Recommendations & Weak Areas ---
    c.setFont("Helvetica-Bold", 16); c.setFillColor(colors.HexColor("#10b981"))
    c.drawString(2*cm, H - 3*cm, "Recommendations & Weak Areas")
    rec_text = "\n".join([f"• {v}" for v in audit["recommendations"].values()])
    weak_text = "\n".join([f"• {w}" for w in audit["weaknesses"]])
    style_body = ParagraphStyle(name="Body", fontName="Helvetica", fontSize=12, leading=16, alignment=TA_LEFT)
    frame3 = Frame(2*cm, 3*cm, W - 4*cm, H - 10*cm, showBoundary=0)
    story3 = [Paragraph("<b>Recommendations</b>", title_style), Paragraph(rec_text, style_body),
              Paragraph("<b>Weak Areas</b>", title_style), Paragraph(weak_text, style_body)]
    frame3.addFromList(story3, c)

    # Footer
    c.setFillColor(colors.HexColor("#6366F1"))
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(2*cm, 2*cm, "FF Tech Elite · Certified Report · Valid for 30 days")
    c.showPage()

    c.save()
    buf.seek(0)
    return buf.getvalue()


# ------------------ Favicon & Health ------------------
def generate_favicon_bytes() -> bytes:
    if PIL_AVAILABLE:
        img = Image.new("RGBA", (32, 32), (99, 102, 241, 255))  # Indigo
        draw = ImageDraw.Draw(img)
        draw.ellipse((6,6,26,26), outline=(255,255,255,220), width=2)
        tmp = io.BytesIO(); img.save(tmp, format="ICO"); tmp.seek(0)
        return tmp.getvalue()
    return b"\x00\x00\x01\x00\x01\x00\x10\x10\x00\x00\x01\x00\x04\x00(\x01\x00\x00\x16\x00\x00\x00" + b"\x00"*64


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    p = os.path.join("static","favicon.ico")
    if os.path.isfile(p):
        with open(p,"rb") as f:
            return Response(content=f.read(), media_type="image/x-icon")
    return Response(content=generate_favicon_bytes(), media_type="image/x-icon")


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status":"ok"})


# ------------------ Serve your HTML ------------------
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ------------------ Open audit endpoints ------------------
@app.get("/run-audit")
def run_audit(url: str, db: Session = Depends(get_db)) -> JSONResponse:
    """
    For 'Python Source Log' link. Returns JSON; persists (open mode: user_id=NULL).
    """
    url  = normalize_url(url)
    data = audit_website(url, deep_crawl_pages=15)

    # previous audit (open mode)
    prev = db.query(Audit).filter(Audit.user_id==None, Audit.url==data["audit"]["website"]["url"])\
           .order_by(Audit.finished_at.desc()).first()
    data["previous_audit"] = {"site_health_score": prev.site_health_score} if prev else None

    a = Audit(
        user_id=None, url=data["audit"]["website"]["url"],
        site_health_score=data["audit"]["site_health_score"], grade=data["audit"]["grade"],
        metrics_summary_json=json.dumps(data["audit"]["metrics_summary"]),
        top_issues_json=json.dumps(data["audit"]["top_issues"]),
        executive_summary=data["audit"]["executive_summary"],
        finished_at=datetime.utcnow(),
    )
    db.add(a); db.commit()
    return JSONResponse(data)


@app.get("/api/audit")
def api_audit(url: str, db: Session = Depends(get_db)) -> JSONResponse:
    """
    AJAX endpoint — used by your JS to update charts and panels.
    """
    return run_audit(url, db)


@app.get("/api/history")
def api_history(url: str, limit: int = Query(12, ge=2, le=50), db: Session = Depends(get_db)) -> JSONResponse:
    url = normalize_url(url)
    rows = db.query(Audit).filter(Audit.user_id==None, Audit.url==url)\
           .order_by(Audit.finished_at.desc()).limit(limit).all()
    points = [{"t": r.finished_at.isoformat(), "score": r.site_health_score} for r in reversed(rows)]
    return JSONResponse({"url": url, "points": points})


@app.get("/api/audit/pdf")
def api_audit_pdf(url: str, db: Session = Depends(get_db)) -> StreamingResponse:
    """
    Generates the 5-page Certified PDF.
    Enforces per-audit download limit = 3.
    We use the latest (most recent) open audit for the URL.
    """
    url = normalize_url(url)
    # Find latest audit for URL (open mode)
    audit_row = db.query(Audit).filter(Audit.user_id==None, Audit.url==url)\
                .order_by(Audit.finished_at.desc()).first()
    if not audit_row:
        # If no stored audit found, generate a temporary one (still enforced later)
        data = audit_website(url, deep_crawl_pages=15)
        audit_row = Audit(
            user_id=None, url=data["audit"]["website"]["url"],
            site_health_score=data["audit"]["site_health_score"], grade=data["audit"]["grade"],
            metrics_summary_json=json.dumps(data["audit"]["metrics_summary"]),
            top_issues_json=json.dumps(data["audit"]["top_issues"]),
            executive_summary=data["audit"]["executive_summary"],
            finished_at=datetime.utcnow(),
        )
        db.add(audit_row); db.commit(); db.refresh(audit_row)

    # Enforce download limit via PdfDownload table
    dl = db.query(PdfDownload).filter(PdfDownload.audit_id == audit_row.id).first()
    if not dl:
        dl = PdfDownload(audit_id=audit_row.id, downloads=0, allowed=3)
        db.add(dl); db.commit(); db.refresh(dl)

    if dl.downloads >= dl.allowed:
        raise HTTPException(status_code=429, detail="PDF download limit reached (3 per audit).")

    # Build audit dict from row
    audit = {
        "website": {"url": audit_row.url},
        "site_health_score": audit_row.site_health_score,
        "grade": audit_row.grade,
        "metrics_summary": json.loads(audit_row.metrics_summary_json),
        "top_issues": json.loads(audit_row.top_issues_json),
        "recommendations": _default_recommendations(),
        "weaknesses": [],  # can reconstruct from top issues (optional)
        "finished_at": audit_row.finished_at.strftime("%b %d, %Y %H:%M"),
        "executive_summary": audit_row.executive_summary,
    }

    pdf_bytes = generate_certified_pdf_5pages(audit)

    # Update counter
    dl.downloads += 1
    dl.last_download = datetime.utcnow()
    db.commit()

    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf",
                             headers={"Content-Disposition": 'attachment; filename="FF-Tech-Elite-Audit.pdf"'})


# ------------------ Magic link auth (email login) ------------------
@app.post("/auth/send-link")
def send_login_link(email: str = Body(...), db: Session = Depends(get_db)) -> JSONResponse:
    """
    Sends a magic login link via email. Verifies on click.
    """
    try:
        validate_email(email)
    except EmailNotValidError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Ensure user exists (create if not)
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, password_hash=pwd_context.hash(os.urandom(8).hex()), is_verified=False, is_admin=False)
        db.add(user); db.commit()

    token = serializer.dumps({"email": email}, salt="magic-link")
    db.add(MagicToken(email=email, token=token)); db.commit()

    link = f"{PUBLIC_URL}/auth/verify?token={token}"
    send_email(email, "Your FF Tech Elite access link", f"Click to log in:\n{link}\n\nLink expires in 24 hours.")
    return JSONResponse({"message":"Login link sent. Please check your email."})


@app.get("/auth/verify", response_class=HTMLResponse)
def verify_magic_link(token: str, db: Session = Depends(get_db)):
    try:
        data = serializer.loads(token, salt="magic-link", max_age=60*60*24)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail="Link expired")
    except BadSignature:
        raise HTTPException(status_code=400, detail="Invalid link")

    email = data.get("email")
    mt = db.query(MagicToken).filter(MagicToken.token == token, MagicToken.email == email).first()
    if not mt or mt.used:
        raise HTTPException(status_code=400, detail="Link already used or invalid")
    mt.used = True; db.commit()

    user = db.query(User).filter(User.email == email).first()
    if user:
        user.is_verified = True; db.commit()

    html = f"""
    <!doctype html><html><body style="font-family:system-ui;padding:2rem">
    <h2>Access granted</h2>
    <p>Welcome, {email}. You can now use authenticated features.</p>
    <p>/Return to the dashboard</a></p>
    </body></html>
    """
    return HTMLResponse(content=html)


# ------------------ Admin login & protected APIs ------------------
@app.post("/auth/admin-login")
def admin_login(email: str = Body(...), password: str = Body(...), db: Session = Depends(get_db)) -> JSONResponse:
    """
    Admin login with seeded credentials (roy.jamshaid@gmail.com / Jamshaid,1981).
    Returns JWT token for protected admin endpoints.
    """
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_admin or not pwd_context.verify(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    token = create_access_token({"sub": user.email, "role": "admin"})
    return JSONResponse({"access_token": token, "token_type": "bearer"})


def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    email   = payload.get("sub")
    role    = payload.get("role")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    user = db.query(User).filter(User.email == email, User.is_admin == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="Admin not found")
    return user


@app.get("/admin/audits")
def admin_audits(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    admin = require_admin(request, db)
    rows = db.query(Audit).order_by(Audit.finished_at.desc()).limit(500).all()
    return JSONResponse({"audits":[
        {"id":a.id,"user_id":a.user_id,"url":a.url,"score":a.site_health_score,"grade":a.grade,"finished_at":a.finished_at.isoformat()}
        for a in rows
    ]})


@app.get("/admin/users")
def admin_users(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    admin = require_admin(request, db)
    rows = db.query(User).order_by(User.created_at.desc()).limit(500).all()
    return JSONResponse({"users":[
        {"id":u.id,"email":u.email,"verified":u.is_verified,"admin":u.is_admin,"created_at":u.created_at.isoformat()}
        for u in rows
    ]})
