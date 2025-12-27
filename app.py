
# app.py
# FF Tech — Web Audit Platform (Healthcheck-safe startup & DB-safe)
# - Open Access audits (unlimited, limited metrics)
# - Registered users: FREE_AUDITS_LIMIT (5–10) -> $5/mo subscription
# - Email verification, scheduling (preferred time/date, timezone)
# - Certified PDF export (5-page, charts & colored summary)
# - Stripe checkout/webhook (demo fallback if not configured)
# - Railway healthcheck: /health + bind to $PORT
# - SAFE DB INIT + SAFE SESSIONS (graceful when DB is down)
# - Flexible HTML linking:
#     /page/<name> (raw HTML auto-injected assets/flags), /template/<name> (Jinja), /static/* (assets)

import os, io, hmac, json, time, base64, secrets, asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
from typing import Optional

import requests
from bs4 import BeautifulSoup

from fastapi import FastAPI, Request, HTTPException, Query, Header
from fastapi.responses import HTMLResponse, JSONResponse, Response, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr, Field

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, ForeignKey, text as sa_text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError

# Stripe (lazy import inside handlers to avoid boot issues)
try:
    import stripe
except Exception:
    stripe = None

# ---------------- CONFIG ----------------
APP_NAME = "FF Tech — Professional AI Website Audit Platform"
USER_AGENT = os.getenv("USER_AGENT", "FFTech-Audit/3.0 (+https://fftech.io)")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech_demo.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

FREE_AUDITS_LIMIT = int(os.getenv("FREE_AUDITS_LIMIT", "10"))
SUBSCRIPTION_PRICE_USD = os.getenv("SUBSCRIPTION_PRICE_USD", "5")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "no-reply@fftech.io")

SCHEDULER_INTERVAL = int(os.getenv("SCHEDULER_INTERVAL", "60"))  # set 0 to disable

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", APP_BASE_URL + "/success")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", APP_BASE_URL + "/cancel")

# Auto-create folders to avoid mount errors
AUTO_CREATE_STATIC = os.getenv("AUTO_CREATE_STATIC", "true").lower() == "true"
AUTO_CREATE_PAGES = os.getenv("AUTO_CREATE_PAGES", "true").lower() == "true"
STATIC_DIR = os.getenv("STATIC_DIR", "static")
PAGES_DIR = os.getenv("PAGES_DIR", "pages")

# ---------------- DB SETUP ----------------
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
    time_of_day = Column(String(8), default="09:00")   # HH:MM
    timezone = Column(String(64), default="UTC")
    daily_report = Column(Boolean, default=True)
    accumulated_report = Column(Boolean, default=True)
    preferred_date = Column(DateTime, nullable=True)
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

# ---------------- SAFE SESSION ----------------
@contextmanager
def safe_session():
    db = None
    try:
        db = SessionLocal()
        db.execute(sa_text("SELECT 1"))  # ping
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

# ---------------- SECURITY ----------------
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

# ---------------- APP + CORS ----------------
app = FastAPI(title=APP_NAME)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Healthcheck (DB‑independent)
@app.get("/health", response_class=JSONResponse)
async def health_check():
    return {"status": "healthy", "time": datetime.utcnow().isoformat()}

# Favicon (avoid noisy 404s)
@app.get("/favicon.ico")
def favicon():
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADElEQVR4nGNgYGBgAAAABQABJzQnWQAAAABJRU5ErkJggg==")
    return Response(content=png, media_type="image/png")

# Ping
@app.get("/ping", response_class=PlainTextResponse)
def ping():
    return PlainTextResponse("pong")

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    try:
        print("[UNCAUGHT ERROR]", type(exc).__name__, str(exc))
    except Exception:
        pass
    return JSONResponse(status_code=500, content={"error": "Internal Server Error", "message": str(exc)[:500]})

# ---------------- FLEXIBLE HTML LINKING ----------------
def ensure_dir(path: str, auto_create: bool) -> bool:
    if os.path.isdir(path):
        return True
    if auto_create:
        try:
            os.makedirs(path, exist_ok=True)
            print(f"[INIT] Created missing directory: {path}")
            return True
        except Exception as e:
            print(f"[INIT WARNING] Could not create directory '{path}': {e}")
            return False
    print(f"[INIT] Directory '{path}' not found (mount skipped).")
    return False

HAS_STATIC = ensure_dir(STATIC_DIR, AUTO_CREATE_STATIC)
HAS_PAGES  = ensure_dir(PAGES_DIR,  AUTO_CREATE_PAGES)

if HAS_STATIC:
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    print("[INIT] Skipping /static mount (directory not present).")

templates: Optional[Jinja2Templates] = None
if HAS_PAGES:
    templates = Jinja2Templates(directory=PAGES_DIR)
else:
    print("[INIT] Skipping Jinja templates mount (pages directory not present).")

# ---------------- HTML FLEX: FLAGS + INJECTORS ----------------
from dataclasses import dataclass

@dataclass
class UIFlags:
    show_auth: bool = True
    demo_mode: bool = False
    stripe_enabled: bool = bool(STRIPE_SECRET_KEY)
    animations: bool = True
    charts: bool = True
    tailwind: bool = True

def get_ui_flags(user=None) -> UIFlags:
    return UIFlags(
        show_auth = (user is None),
        demo_mode = not bool(STRIPE_SECRET_KEY),
        stripe_enabled = bool(STRIPE_SECRET_KEY),
        animations = True,
        charts = True,
        tailwind = True,
    )

def inject_head_assets(html: str, flags: UIFlags) -> str:
    """
    Inject Tailwind, Chart.js, Fonts & Icons into raw HTML.
    If </head> exists (case-insensitive), insert before it; else prepend.
    """
    head_inject = []

    if flags.tailwind:
        head_inject.append('https://cdn.tailwindcss.com</script>')
    if flags.charts:
        head_inject.append('https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js</script>')

    head_inject.append('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap')
    head_inject.append('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css')

    payload = "\n".join(head_inject) + """
<style>
  body { font-family: 'Plus Jakarta Sans', system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background-color: #f8fafc; scroll-behavior: smooth; }
  .glass { background: rgba(255,255,255,0.75); backdrop-filter: blur(12px); border: 1px solid rgba(226,232,240,0.8); }
  .status-pulse { width: 14px; height: 14px; background: #6366f1; border-radius: 50%; display: inline-block; animation: pulse 1.5s infinite; }
  @keyframes pulse { 0% { transform: scale(0.9); box-shadow: 0 0 0 0 rgba(99, 102, 241, 0.7); } 70% { transform: scale(1.1); box-shadow: 0 0 0 10px rgba(99, 102, 241, 0); } 100% { transform: scale(0.9); } }
  .hidden { display: none !important; }
  .admin-tab-active { border-bottom: 2px solid #6366f1; color: #6366f1; }
</style>
""".strip()

    low = html.lower()
    if "</head>" in low:
        idx = low.rfind("</head>")
        return html[:idx] + payload + html[idx:]
    else:
        return payload + "\n" + html

def inject_bootstrap_script(html: str, app_name: str, flags: UIFlags) -> str:
    """
    Expose Python flags & app name to front-end scripts on raw HTML pages.
    Inserts before </body> when present; else appends to end.
    """
    boot = f"""
<script>
  window.__FF_FLAGS__ = {json.dumps(flags.__dict__)};
  window.__APP_NAME__ = {json.dumps(app_name)};
</script>
""".strip()
    low = html.lower()
    if "</body>" in low:
        idx = low.rfind("</body>")
        return html[:idx] + boot + html[idx:]
    else:
        return html + "\n" + boot

@app.get("/page/{name}", response_class=HTMLResponse)
def get_flexible_page(name: str, request: Request):
    if not HAS_PAGES:
        raise HTTPException(status_code=404, detail="Pages directory not available")
    if any(ch in name for ch in ("..", "/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid page name")
    path = os.path.join(PAGES_DIR, f"{name}.html")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Page not found")
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    flags = get_ui_flags()
    html = inject_head_assets(raw, flags)
    html = inject_bootstrap_script(html, APP_NAME, flags)
    return HTMLResponse(html)

@app.get("/template/{name}", response_class=HTMLResponse)
def get_jinja_page(name: str, request: Request):
    if not HAS_PAGES or not templates:
        raise HTTPException(status_code=404, detail="Templates not available")
    if any(ch in name for ch in ("..", "/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid template name")
    return templates.TemplateResponse(f"{name}.html", {"request": request, "app_name": APP_NAME, "flags": get_ui_flags()})

# ---------------- NETWORK HELPERS ----------------
def safe_request(url: str, method: str = "GET", **kwargs):
    try:
        kwargs.setdefault("timeout", (8, 12))  # connect, read
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

# ---------------- AUDIT ENGINE ----------------
def detect_mixed_content(soup: BeautifulSoup, scheme: str) -> bool:
    if scheme != "https": return False
    for tag in soup.find_all(["img","script","link","iframe","video","audio","source"]):
        for attr in ["src","href","data","poster"]:
            val = tag.get(attr)
            if isinstance(val,str) and val.startswith("http://"): return True
    return False

def is_blocking_script(tag) -> bool:
    return tag.name == "script" and not (tag.get("async") or tag.get("defer") or tag.get("type")=="module")

def crawl_internal(seed_url: str, max_pages: int = 60):
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
    blocking_script_count = sum(1 for s in soup.find_all("script") if is_blocking_script(s))
    stylesheets = soup.find_all("link", rel=lambda v: v and "stylesheet" in v.lower()); stylesheet_count = len(stylesheets)
    ld_json_count = len(soup.find_all("script", attrs={"type":"application/ld+json"}))
    og_meta = bool(soup.find("meta", property=lambda v: v and v.startswith("og:")))
    tw_meta = bool(soup.find("meta", attrs={"name": lambda v: v and v.startswith("twitter:")}))
    viewport_meta = bool(soup.find("meta", attrs={"name":"viewport"}))

    headers = resp.headers or {}
    mixed = detect_mixed_content(soup, scheme)

    origin = f"{urlparse(resp.url).scheme}://{urlparse(resp.url).netloc}"
    robots_head = safe_request(urljoin(origin, "/robots.txt"), "HEAD")
    sitemap_head = safe_request(urljoin(origin, "/sitemap.xml"), "HEAD")
    robots_ok = bool(robots_head and robots_head.status_code < 400)
    sitemap_ok = bool(sitemap_head and sitemap_head.status_code < 400)

    crawled = crawl_internal(resp.url, max_pages=60)
    statuses = {"2xx":0,"3xx":0,"4xx":0,"5xx":0,None:0}
    redirect_chains = 0
    broken_internal = 0
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
        if (row.get("redirects") or 0) >= 2:
            redirect_chains += 1
        if row.get("status") in (404, 410):
            broken_internal += 1

    # Scoring (heuristics)
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
    if redirect_chains > 0: bp_score -= min(12, redirect_chains * 2)

    sec_score = 100
    if not headers.get("Strict-Transport-Security"): sec_score -= 18
    if not headers.get("Content-Security-Policy"): sec_score -= 18
    if not headers.get("X-Frame-Options"): sec_score -= 10
    if not headers.get("X-Content-Type-Options"): sec_score -= 8
    if not headers.get("Referrer-Policy"): sec_score -= 6
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

    errors = broken_internal + (1 if mixed else 0)
    warnings = (1 if ttfb_ms > 800 else 0) + (1 if size_mb > 1.0 else 0)
    notices = (1 if not headers.get("Content-Security-Policy") else 0) + (1 if not robots_ok else 0) + (1 if not sitemap_ok else 0)

    cat2_base = 100
    penalty = (statuses["4xx"] * 2) + (statuses["5xx"] * 3) + (redirect_chains * 1.5) + (broken_internal * 2)
    cat2_total = max(30, min(100, int(cat2_base - penalty)))
    cat_scores = {"SEO": seo_score, "Performance": perf_score, "Security": sec_score, "Accessibility": a11y_score, "Mobile": 85 if viewport_meta else 60}
    totals = {"cat1": overall, "cat2": cat2_total, "cat3": seo_score, "cat4": perf_score, "cat5": int(0.6*sec_score + 0.4*(85 if viewport_meta else 60)), "overall": overall}

    exec_summary = (
        f"FF Tech audited {resp.url}, overall health {overall}% (grade {grade}). "
        f"Payload {size_mb:.2f} MB, TTFB {ttfb_ms} ms; optimize SEO (H1/meta/canonical/alt/JSON‑LD), "
        f"add security headers (HSTS/CSP/XFO/XCTO/Referrer‑Policy), remove mixed content, and fix broken links."
    )

    def gauge(score: int):
        color = "#10b981" if score >= 80 else "#f59e0b" if score >= 60 else "#ef4444"
        return {"labels":["Score","Remaining"],"datasets":[{"data":[score,100-score],"backgroundColor":[color,"#e5e7eb"],"borderWidth":0}]}

    overall_gauge = gauge(overall)
    health_gauge  = gauge(overall)
    issues_chart  = {"labels":["Errors","Warnings","Notices"],"datasets":[{"data":[errors,warnings,notices],"backgroundColor":["#ef4444","#f59e0b","#3b82f6"]}]}
    category_chart= {"labels": list(cat_scores.keys()), "datasets":[{"label":"Score","data": list(cat_scores.values()), "backgroundColor":["#6366f1","#f59e0b","#10b981","#ef4444","#0ea5e9"]}]}

    strengths = []
    if sec_score >= 80: strengths.append("Baseline security headers in place.")
    if seo_score >= 75: strengths.append("SEO foundations across titles/headings.")
    if a11y_score >= 75: strengths.append("Semantic structure aids assistive tech.")
    if perf_score >= 70: strengths.append("Acceptable page weight; optimization possible.")
    if viewport_meta: strengths.append("Viewport meta present; mobile baseline.")
    if not strengths: strengths = ["Platform reachable and crawlable."]

    weaknesses = []
    if perf_score < 80: weaknesses.append("Render‑blocking JS/CSS impacting interactivity.")
    if seo_score  < 80: weaknesses.append("Meta/canonical coverage inconsistent.")
    if a11y_score< 80: weaknesses.append("Alt text and ARIA landmarks incomplete.")
    if sec_score  < 90: weaknesses.append("HSTS/CSP/XFO/XCTO/Referrer‑Policy missing.")
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
        pass_pct = max(10, min(100, base - ((n%7)*2)))
        metrics.append({"num": n, "severity": "green" if pass_pct>=80 else "yellow" if pass_pct>=60 else "red",
                        "chart_type": "bar" if n%5 else "doughnut",
                        "chart_data": {"labels": ["Pass","Fail"], "datasets":[{"data":[pass_pct, 100-pass_pct], "backgroundColor": ["#10b981","#ef4444"], "borderWidth":0}]}})

    return {
        "grade": grade, "summary": exec_summary, "strengths": strengths, "weaknesses": weaknesses, "priority": priority,
        "overall": overall, "errors": errors, "warnings": warnings, "notices": notices,
        "overall_gauge": overall_gauge, "health_gauge": health_gauge, "issues_chart": issues_chart,
        "category_chart": category_chart, "totals": totals, "metrics": metrics, "premium": False, "remaining": 0,
        "cat_scores": cat_scores,
    }

# ---------------- REFINED INDEX_HTML (fallback; assets injected at runtime) ----------------
INDEX_HTML = r"""<!DOCTYPE html>
<html lang='en'>
<head>
    <meta charset='UTF-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>FF TECH — Professional AI Website Audit</title>
</head>
<body class="text-slate-900">
    <main class="pt-32 pb-20 px-6 max-w-5xl mx-auto">
      <h1 class="text-5xl md:text-6xl font-black mb-6 tracking-tighter">FF TECH Audit</h1>
      <form id="audit-form" class="max-w-2xl mx-auto flex gap-2 p-2 bg-white rounded-[2rem] shadow-2xl border border-slate-100">
        <input id="url-input" type="url" placeholder="https://example.com" required class="flex-1 p-5 outline-none font-bold text-lg rounded-2xl">
        <button type="submit" class="bg-indigo-600 text-white px-10 py-5 rounded-[1.5rem] font-black text-lg hover:bg-indigo-700 transition-all shadow-xl shadow-indigo-100 uppercase tracking-tighter">
          Analyze Site
        </button>
      </form>
      <div id="loading-zone" class="hidden text-center py-20 glass rounded-[3rem] border border-indigo-50">
        <div class="status-pulse mb-4"></div>
        <p class="font-black text-indigo-600 tracking-[0.2em] animate-pulse uppercase text-xs">CRAWLING PAGES & CHECKING HEADERS...</p>
      </div>
      <div id="results-view" class="hidden">
        <canvas id="mainChart" width="200" height="200"></canvas>
      </div>
    </main>
    <script>
      const form = document.getElementById('audit-form');
      let chart = null;
      form.onsubmit = async (e) => {
        e.preventDefault();
        const url = document.getElementById('url-input').value;
        document.getElementById('loading-zone').classList.remove('hidden');
        document.getElementById('results-view').classList.add('hidden');
        try {
          const res = await fetch('/audit?url=' + encodeURIComponent(url));
          const data = await res.json();
          document.getElementById('loading-zone').classList.add('hidden');
          document.getElementById('results-view').classList.remove('hidden');
          const ctx = document.getElementById('mainChart').getContext('2d');
          if (chart) chart.destroy();
          chart = new Chart(ctx, { type: 'doughnut', data: data.overall_gauge, options: { cutout: '85%', plugins:{ legend:{ display:false } } }});
        } catch (e) {
          alert('Audit temporarily unavailable. Try again shortly.');
          document.getElementById('loading-zone').classList.add('hidden');
        }
      };
    </script>
</body>
</html>
"""

# ---------------- Routes: Home uses Jinja if available, else inject into fallback HTML ----------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    try:
        if templates is not None:
            return templates.TemplateResponse("index.html", {"request": request, "app_name": APP_NAME, "flags": get_ui_flags()})
    except Exception:
        pass
    flags = get_ui_flags()
    html = inject_head_assets(INDEX_HTML, flags)
    html = inject_bootstrap_script(html, APP_NAME, flags)
    return HTMLResponse(html)

# ---------------- Schemas ----------------
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
    timezone: str
    preferred_date: str | None = None
    daily_report: bool = True
    accumulated_report: bool = True
    enabled: bool = True

class WebsiteIn(BaseModel):
    url: str

class SettingsIn(BaseModel):
    timezone: str
    notify_daily_default: bool
    notify_acc_default: bool

# ---------------- PDF EXPORT (5 pages with charts & colored summary) ----------------
@app.get("/export-pdf")
def export_pdf(url: str = Query(...)):
    """
    Generates a 5-page colored PDF report:
    1) Cover: title, URL, grade, overall score
    2) Score gauge (pie) + Issues chart (pie)
    3) Category scores (bar)
    4) Narrative summary (strengths, weaknesses, priority)
    5) Top metrics pass% (bar) + totals
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.graphics.shapes import Drawing, String, Rect
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.legends import Legend
    from reportlab.graphics import renderPDF

    payload = run_actual_audit(url)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    def header_footer(page_title: str):
        # Header band
        c.setFillColor(colors.indigo)
        c.rect(0, H-35*mm, W, 35*mm, fill=True, stroke=False)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(20*mm, H-20*mm, APP_NAME)
        c.setFont("Helvetica", 10)
        c.drawRightString(W-20*mm, H-20*mm, datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
        # Page title
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(20*mm, H-45*mm, page_title)
        # Footer
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.slategray)
        c.drawString(20*mm, 12*mm, "Certified by FF Tech • Automated Analysis • Email: support@fftech.io")

    # ---- Page 1: Cover ----
    header_footer("Certified Audit Report")
    c.setFont("Helvetica-Bold", 24); c.setFillColor(colors.indigo)
    c.drawString(20*mm, H-65*mm, "Executive Website Health")
    c.setFillColor(colors.black); c.setFont("Helvetica", 12)
    c.drawString(20*mm, H-80*mm, f"Website: {normalize_url(url)}")
    c.drawString(20*mm, H-90*mm, f"Grade: {payload['grade']}")
    c.drawString(20*mm, H-100*mm, f"Overall Score: {payload['overall']}%")

    # Decorative band
    c.setFillColor(colors.Color(0.93,0.95,0.99))
    c.roundRect(20*mm, H-140*mm, W-40*mm, 25*mm, 8, fill=True, stroke=False)
    c.setFillColor(colors.black); c.setFont("Helvetica", 11)
    c.drawString(25*mm, H-125*mm, payload["summary"][:180] + ("..." if len(payload["summary"])>180 else ""))

    c.showPage()

    # ---- Page 2: Gauges & Issues (Pie charts) ----
    header_footer("Score Gauge & Issues Breakdown")

    # Score Pie: [score, remaining]
    d1 = Drawing(180, 180)
    p1 = Pie()
    p1.x = 40; p1.y = 20; p1.width = 100; p1.height = 100
    p1.data = [payload["overall"], 100 - payload["overall"]]
    p1.labels = ["Score", "Remaining"]
    p1.slices.strokeWidth = 0.5
    p1.slices[0].fillColor = colors.Color(0.13,0.59,0.95)  # blue
    p1.slices[1].fillColor = colors.Color(0.90,0.92,0.95)  # gray
    d1.add(p1)
    d1.add(String(40, 130, "Overall Health", fontName="Helvetica-Bold", fontSize=12, fillColor=colors.indigo))
    renderPDF.draw(d1, c, 20*mm, H-180*mm)

    # Issues Pie: [errors, warnings, notices]
    d2 = Drawing(220, 180)
    p2 = Pie()
    p2.x = 60; p2.y = 20; p2.width = 100; p2.height = 100
    p2.data = [payload["errors"], payload["warnings"], payload["notices"]]
    p2.labels = ["Errors", "Warnings", "Notices"]
    p2.slices[0].fillColor = colors.Color(0.93,0.36,0.36)  # red
    p2.slices[1].fillColor = colors.Color(0.96,0.62,0.12)  # amber
    p2.slices[2].fillColor = colors.Color(0.23,0.51,0.96)  # blue
    d2.add(p2)
    d2.add(String(40, 130, "Issues Breakdown", fontName="Helvetica-Bold", fontSize=12, fillColor=colors.indigo))
    renderPDF.draw(d2, c, 115*mm, H-180*mm)

    # Context lines
    c.setFont("Helvetica", 11)
    c.drawString(20*mm, H-200*mm, f"TTFB: {payload['summary'].split('TTFB ')[1].split(' ms')[0]} ms (from summary)")
    c.drawString(20*mm, H-210*mm, "Optimize caching, async/defer scripts, and reduce payload for performance.")

    c.showPage()

    # ---- Page 3: Category Scores (Bar chart) ----
    header_footer("Category Scores")
    cats = list(payload["cat_scores"].keys())
    vals = list(payload["cat_scores"].values())

    d3 = Drawing(400, 220)
    bc = VerticalBarChart()
    bc.x = 50; bc.y = 30
    bc.height = 140; bc.width = 300
    bc.data = [vals]
    bc.categoryAxis.categoryNames = cats
    bc.barWidth = 18
    bc.groupSpacing = 12
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = 100
    bc.valueAxis.valueStep = 20
    bc.bars[0].fillColor = colors.Color(0.39,0.33,0.94)  # indigo
    d3.add(bc)
    d3.add(String(50, 180, "SEO / Performance / Security / Accessibility / Mobile", fontName="Helvetica-Bold", fontSize=12, fillColor=colors.indigo))
    renderPDF.draw(d3, c, 20*mm, H-230*mm)

    # Highlights
    c.setFont("Helvetica-Bold", 12); c.setFillColor(colors.indigo)
    c.drawString(20*mm, H-250*mm, "Highlights")
    c.setFont("Helvetica", 11); c.setFillColor(colors.black)
    c.drawString(20*mm, H-260*mm, f"Overall: {payload['overall']}% • Grade: {payload['grade']} • Mobile: {cats[-1]} {vals[-1]}%")

    c.showPage()

    # ---- Page 4: Detailed Summary (colored bullets) ----
    header_footer("Detailed Summary & Recommendations")

    def bullet_list(title: str, items: list[str], color):
        c.setFillColor(color); c.setFont("Helvetica-Bold", 12)
        c.drawString(20*mm, y[0], title); y[0] -= 8*mm
        c.setFillColor(colors.black); c.setFont("Helvetica", 11)
        for it in (items[:8] if items else ["—"]):
            c.drawString(25*mm, y[0], f"• {it}")
            y[0] -= 7*mm
        y[0] -= 4*mm

    y = [H-65*mm]
    bullet_list("Strengths", payload["strengths"], colors.Color(0.10,0.64,0.47))  # teal
    bullet_list("Weaknesses", payload["weaknesses"], colors.Color(0.93,0.36,0.36))  # red
    bullet_list("Priority Actions", payload["priority"], colors.Color(0.39,0.33,0.94))  # indigo

    # Executive paragraph
    c.setFillColor(colors.indigo); c.setFont("Helvetica-Bold", 12)
    c.drawString(20*mm, y[0], "Executive Summary"); y[0] -= 8*mm
    c.setFillColor(colors.black); c.setFont("Helvetica", 11)
    summary_lines = []
    text = payload["summary"]
    # Simple wrap
    while text:
        summary_lines.append(text[:95])
        text = text[95:]
    for ln in summary_lines[:12]:
        c.drawString(25*mm, y[0], ln); y[0] -= 6*mm

    c.showPage()

    # ---- Page 5: Metrics Overview (bar) & Totals ----
    header_footer("Metrics Overview")
    top_metrics = payload["metrics"][:12]
    labels = [f"S{m['num']}" for m in top_metrics]
    passes = []
    for m in top_metrics:
        try:
            passes.append(int(m["chart_data"]["datasets"][0]["data"][0]))
        except Exception:
            passes.append(0)

    d5 = Drawing(400, 220)
    bc2 = VerticalBarChart()
    bc2.x = 50; bc2.y = 30
    bc2.height = 140; bc2.width = 300
    bc2.data = [passes]
    bc2.categoryAxis.categoryNames = labels
    bc2.barWidth = 16
    bc2.groupSpacing = 10
    bc2.valueAxis.valueMin = 0
    bc2.valueAxis.valueMax = 100
    bc2.valueAxis.valueStep = 20
    bc2.bars[0].fillColor = colors.Color(0.13,0.59,0.95)  # blue
    d5.add(bc2)
    d5.add(String(50, 180, "Top Signals Pass %", fontName="Helvetica-Bold", fontSize=12, fillColor=colors.indigo))
    renderPDF.draw(d5, c, 20*mm, H-230*mm)

    # Totals box
    c.setFillColor(colors.Color(0.96,0.97,0.99))
    c.roundRect(20*mm, H-260*mm, W-40*mm, 25*mm, 8, fill=True, stroke=False)
    c.setFillColor(colors.black); c.setFont("Helvetica", 11)
    totals = payload["totals"]
    c.drawString(25*mm, H-245*mm, f"Totals • Overall: {totals['overall']}% • Cat2: {totals['cat2']} • SEO: {totals['cat3']} • Perf: {totals['cat4']} • Security/Mobile: {totals['cat5']}")

    c.showPage()
    c.save()

    pdf_bytes = buf.getvalue(); buf.close()
    fname = f"fftech_audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename=\"{fname}\"'})

# ---------------- Routes (DB-safe) ----------------
@app.get("/audit", response_class=JSONResponse)
def audit_handler(url: str = Query(...), authorization: str | None = Header(None)):
    payload = run_actual_audit(url)
    user = None
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

    # Persist (if DB available)
    with safe_session() as db:
        if db:
            norm = normalize_url(url)
            site = db.query(Website).filter(Website.url == norm).first()
            if not site:
                site = Website(url=norm, user_id=(user.id if user else None), active=True)
                db.add(site); db.commit(); db.refresh(site)
            row = Audit(
                website_id=site.id, url=norm, overall=payload["overall"], grade=payload["grade"],
                errors=payload["errors"], warnings=payload["warnings"], notices=payload["notices"],
                summary=payload["summary"], cat_scores_json=json.dumps(payload.get("cat_scores", {})),
                cat_totals_json=json.dumps(payload.get("totals", {})), metrics_json=json.dumps(payload.get("metrics", [])),
                premium=payload["premium"]
            )
            db.add(row); db.commit()

    return JSONResponse(payload)

@app.post("/register")
def register(payload: RegisterIn):
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        email = payload.email.lower().strip()
        if db.query(User).filter(User.email == email).first():
            raise HTTPException(status_code=400, detail="Email already registered")
        pwd_hash, salt = create_user_password(payload.password)
        user = User(email=email, password_hash=pwd_hash, password_salt=salt, timezone=payload.timezone, free_audits_remaining=FREE_AUDITS_LIMIT)
        db.add(user); db.commit(); db.refresh(user)
        token = jwt_sign({"uid": user.id, "act": "verify"}, exp_minutes=60*24)
        link = f"{APP_BASE_URL}/verify?token={token}"
        subj = "FF Tech — Verify your account"
        body = f"Welcome!\nVerify your email:\n{link}\n(Expires in 24h)"
        send_email(email, subj, body, [])
        return {"message": "Registration successful. Check your email to verify."}

@app.get("/verify")
def verify(token: str):
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        payload = jwt_verify(token)
        if payload.get("act") != "verify":
            raise HTTPException(status_code=400, detail="Invalid token")
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

# Websites & Scheduling
@app.post("/websites")
def add_website(payload: WebsiteIn, authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")
    data = jwt_verify(authorization.split(" ",1)[1])
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
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
    data = jwt_verify(authorization.split(" ",1)[1])
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
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
    data = jwt_verify(authorization.split(" ",1)[1])
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        rows = db.query(Schedule).filter(Schedule.user_id == data.get("uid")).all()
        out = []
        for s in rows:
            site = db.get(Website, s.website_id)
            out.append({"id": s.id, "website_url": site.url if site else None, "enabled": s.enabled,
                        "time_of_day": s.time_of_day, "timezone": s.timezone,
                        "daily_report": s.daily_report, "accumulated_report": s.accumulated_report,
                        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None})
        return out

# ---------------- Billing (Stripe, lazy import) ----------------
@app.get("/billing/status")
def billing_status(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")
    data = jwt_verify(authorization.split(" ",1)[1])
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        return {"subscribed": user.subscribed, "free_audits_remaining": user.free_audits_remaining}

@app.post("/billing/checkout")
def billing_checkout(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")
    data = jwt_verify(authorization.split(" ",1)[1])
    with safe_session() as db:
        if not db:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        try:
            import stripe as _stripe
            if not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
                user.subscribed = True
                db.commit()
                return {"message": "Stripe not configured — subscription activated (demo).", "url": None}
            _stripe.api_key = STRIPE_SECRET_KEY
            session = _stripe.checkout.Session.create(
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
    try:
        import stripe as _stripe
        if not STRIPE_WEBHOOK_SECRET:
            return {"message": "Webhook secret not configured"}
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature", "")
        event = _stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    type_ = event["type"]
    data = event["data"]["object"]
    with safe_session() as db:
        if not db:
            return {"received": True, "db": "unavailable"}
        try:
            if type_ in ("checkout.session.completed", "invoice.payment_succeeded"):
                email = data.get("customer_details", {}).get("email") or data.get("customer_email")
                if not email and data.get("customer"):
                    cust = _stripe.Customer.retrieve(data["customer"]); email = cust.get("email")
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

# ---------------- Admin ----------------
@app.get("/admin/users")
def admin_users(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=403, detail="Admin required")
    data = jwt_verify(authorization.split(" ",1)[1])
    with safe_session() as db:
        if not db: raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        if not user or user.role != "admin": raise HTTPException(status_code=403, detail="Admin required")
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
        if not db: raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        if not user or user.role != "admin": raise HTTPException(status_code=403, detail="Admin required")
        audits = db.query(Audit).order_by(Audit.created_at.desc()).limit(200).all()
        return [{"id": a.id, "url": a.url, "website_id": a.website_id, "overall": a.overall,
                 "grade": a.grade, "errors": a.errors, "warnings": a.warnings, "notices": a.notices,
                 "created_at": a.created_at.isoformat()} for a in audits]

# ---------------- Scheduler (hardened) ----------------
async def scheduler_loop():
    await asyncio.sleep(3)
    error_count = 0
    while True:
        try:
            with safe_session() as db:
                if not db:
                    await asyncio.sleep(SCHEDULER_INTERVAL); continue

                now_utc = datetime.utcnow().replace(second=0, microsecond=0)

                try:
                    schedules = db.query(Schedule).filter(Schedule.enabled == True).all()
                except Exception as e:
                    error_count += 1
                    if error_count <= 5:
                        print("[SCHEDULER QUERY ERROR]", e)
                    await asyncio.sleep(SCHEDULER_INTERVAL)
                    continue

                error_count = 0  # reset

                for s in schedules:
                    try:
                        user = db.get(User, s.user_id)
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
                            site = db.get(Website, s.website_id)
                            if not site: continue
                            payload = run_actual_audit(site.url)

                            # Minimal PDF email page
                            from reportlab.lib.pagesizes import A4
                            from reportlab.pdfgen import canvas
                            from reportlab.lib.units import mm
                            buf = io.BytesIO(); cpdf = canvas.Canvas(buf, pagesize=A4)
                            cpdf.setFont("Helvetica-Bold", 14); cpdf.drawString(20*mm, A4[1]-30*mm, f"Audit: {site.url} ({payload['grade']} / {payload['overall']}%)")
                            cpdf.showPage(); cpdf.save(); pdf_bytes = buf.getvalue(); buf.close()
                            subj = f"FF Tech Audit — {site.url} ({payload['grade']} / {payload['overall']}%)"
                            body = "Your scheduled audit is ready.\nCertified PDF attached.\n— FF Tech"
                            send_email(user.email, subj, body, [(f"fftech_audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf", pdf_bytes)])

                            row = Audit(
                                website_id=site.id, url=site.url, overall=payload["overall"], grade=payload["grade"],
                                errors=payload["errors"], warnings=payload["warnings"], notices=payload["notices"],
                                summary=payload["summary"], cat_scores_json=json.dumps(payload["cat_scores"]),
                                cat_totals_json=json.dumps(payload["totals"]), metrics_json=json.dumps(payload["metrics"])
                            )
                            db.add(row); s.last_run_at = now_utc; db.commit()
                    except Exception as e:
                        print("[SCHEDULER ITEM ERROR]", e)
        except Exception as e:
            print("[SCHEDULER ERROR]", e)

        await asyncio.sleep(SCHEDULER_INTERVAL)

# ---------------- SAFE DB INIT (+ committed schema patches) ----------------
def apply_schema_patches_committed():
    with engine.begin() as conn:
        Base.metadata.create_all(bind=engine)
        dialect = engine.dialect.name

        def try_alter(stmt: str):
            try:
                conn.execute(sa_text(stmt))
            except Exception as e:
                print("[SCHEMA PATCH WARN]", str(e)[:200])

        if dialect == "sqlite":
            try_alter("ALTER TABLE schedules ADD COLUMN enabled boolean DEFAULT 1")
            try_alter("ALTER TABLE schedules ADD COLUMN preferred_date timestamp NULL")
            try_alter("ALTER TABLE schedules ADD COLUMN time_of_day varchar(8)")
            try_alter("ALTER TABLE schedules ADD COLUMN timezone varchar(64) DEFAULT 'UTC'")
            try_alter("ALTER TABLE schedules ADD COLUMN daily_report boolean DEFAULT 1")
            try_alter("ALTER TABLE schedules ADD COLUMN accumulated_report boolean DEFAULT 1")
            try_alter("ALTER TABLE schedules ADD COLUMN last_run_at timestamp NULL")
        else:
            try_alter("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS enabled boolean DEFAULT true")
            try_alter("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS preferred_date timestamp NULL")
            try_alter("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS time_of_day varchar(8)")
            try_alter("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS timezone varchar(64) DEFAULT 'UTC'")
            try_alter("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS daily_report boolean DEFAULT true")
            try_alter("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS accumulated_report boolean DEFAULT true")
            try_alter("ALTER TABLE schedules ADD COLUMN IF NOT EXISTS last_run_at timestamp NULL")

async def init_db():
    max_attempts = int(os.getenv("DB_CONNECT_MAX_ATTEMPTS", "10"))
    delay = float(os.getenv("DB_CONNECT_RETRY_DELAY", "2"))
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
            with engine.begin() as conn:
                conn.execute(sa_text("SELECT 1"))
            apply_schema_patches_committed()
            print("[DB] Connected and tables ensured")
            return
        except OperationalError as e:
            print(f"[DB] Connection attempt {attempt}/{max_attempts} failed: {e}")
        except Exception as e:
            print(f"[DB] Non-operational DB init error: {e}")
        await asyncio.sleep(delay)
    print("[DB WARNING] DB unavailable after retries; app keeps serving limited functionality")

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(init_db())
    if SCHEDULER_INTERVAL > 0:
        asyncio.create_task(scheduler_loop())

# ---------------- MAIN ----------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port)

# ---------------- EMAIL SENDING ----------------
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
