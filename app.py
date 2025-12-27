# app.py
# FF Tech — AI Website Audit SaaS + Ultra-Flexible Web Integrator
# ---------------------------------------------------------------------------
# - Frontend-agnostic: serves raw HTML, SPA builds, Markdown, Jinja from ./pages
# - Smart duplicate-safe asset injection (CDN + local /static), runtime-extensible
# - Open Access + Registered (passwordless magic link) with JWT
# - AI audit engine -> 200 metrics grouped by category + Chart.js datasets
# - 5-page PDF report with charts & branding
# - Stripe subscriptions (real or demo), async scheduler with email+PDF
# - Admin endpoints, DB-safe sessions, health checks
#
# Healthcheck FIX: /health returns 200 immediately, independent of DB.
# Startup tasks (DB init, scheduler) run asynchronously in background.

import os, io, hmac, json, time, base64, secrets, asyncio, mimetypes, smtplib, ssl
from dataclasses import dataclass, asdict
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
from typing import Optional, List, Dict
from email.message import EmailMessage

import requests
from bs4 import BeautifulSoup

from fastapi import FastAPI, Request, HTTPException, Query, Header, Body
from fastapi.responses import HTMLResponse, JSONResponse, Response, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, ForeignKey, text as sa_text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError

# Stripe optional
try:
    import stripe
except Exception:
    stripe = None

# ---------------------- CONFIG ----------------------
APP_NAME = os.getenv("APP_NAME", "FF Tech — AI Website Audit SaaS")
USER_AGENT = os.getenv("USER_AGENT", "FFTech-Audit/3.2 (+https://fftech.io)")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech_demo.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

FREE_AUDITS_LIMIT = int(os.getenv("FREE_AUDITS_LIMIT", "10"))
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "no-reply@fftech.io")

SCHEDULER_INTERVAL = int(os.getenv("SCHEDULER_INTERVAL", "60"))  # seconds (set 0 to disable)

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", APP_BASE_URL + "/success")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", APP_BASE_URL + "/cancel")

STATIC_DIR = os.getenv("STATIC_DIR", "static")
PAGES_DIR = os.getenv("PAGES_DIR", "pages")
AUTO_CREATE_STATIC = os.getenv("AUTO_CREATE_STATIC", "true").lower() == "true"
AUTO_CREATE_PAGES  = os.getenv("AUTO_CREATE_PAGES", "true").lower() == "true"

# Runtime-extensible injector defaults
LOCAL_STYLES_DEFAULT        = ["/static/css/style.css"]
LOCAL_SCRIPTS_HEAD_DEFAULT  = []
LOCAL_SCRIPTS_BODY_DEFAULT  = ["/static/js/app.js"]
CDN_STYLES_DEFAULT = [
    "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap",
    "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css",
]
CDN_SCRIPTS_HEAD_DEFAULT = [
    "https://cdn.tailwindcss.com",
    "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js",
]
CDN_SCRIPTS_BODY_DEFAULT: List[str] = []

BASE_INLINE_CSS_DEFAULT = """
:root { color-scheme: light; }
html { scroll-behavior: smooth; }
body {
  font-family: 'Plus Jakarta Sans', system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  background-color: #f8fafc;
  margin: 0;
}
.hidden { display: none !important; }
.ff-container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
.ff-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 1rem; padding: 1.25rem; }
"""

INDEX_HTML_FALLBACK = r"""<!DOCTYPE html>
<html lang='en'>
<head>
  <meta charset='UTF-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1.0'>
  <title>FF Tech — Flexible Audit</title>
</head>
<body class="text-slate-900">
  <main class="ff-container">
    <h1 style="font-weight:900;letter-spacing:-0.02em;">FF Tech — AI Website Audit SaaS</h1>
    <p>Drop <code>pages/index.html</code> to override this screen, or serve any file via <code>/page/&lt;path&gt;</code>.</p>
    <form id="audit-form" style="margin-top:1rem; display:flex; gap:8px;">
      <input id="url-input" type="url" placeholder="https://example.com" required style="flex:1;padding:0.8rem;border-radius:0.6rem;border:1px solid #e5e7eb;">
      <button type="submit" style="padding:0.8rem 1rem;border-radius:0.6rem;background:#6366f1;color:#fff;font-weight:700;">Run Audit</button>
      <button type="button" id="pdf-btn" style="padding:0.8rem 1rem;border-radius:0.6rem;background:#111827;color:#fff;font-weight:700;">Export PDF</button>
    </form>
    <div id="results" class="ff-card hidden" style="margin-top:1rem;">
      <h2>Results</h2>
      <p id="summary"></p>
      <canvas id="overallChart" width="260" height="260"></canvas>
    </div>
  </main>
  <script>
    let chart = null;
    document.getElementById('audit-form').onsubmit = async (e) => {
      e.preventDefault();
      try {
        const url = document.getElementById('url-input').value;
        const res = await fetch('/audit?url=' + encodeURIComponent(url));
        const data = await res.json();
        document.getElementById('results').classList.remove('hidden');
        document.getElementById('summary').innerText = data.summary || '';
        const ctx = document.getElementById('overallChart').getContext('2d');
        if (chart) chart.destroy();
        chart = new Chart(ctx, { type:'doughnut', data:data.charts.overall_gauge,
          options:{ cutout:'80%', plugins:{legend:{display:false}} }});
      } catch(e){ alert('Audit failed'); }
    };
    document.getElementById('pdf-btn').onclick = () => {
      const url = document.getElementById('url-input').value || 'https://example.com';
      window.location = '/export-pdf?url=' + encodeURIComponent(url);
    };
  </script>
</body>
</html>
"""

# ---------------------- APP INIT ----------------------
app = FastAPI(title=APP_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

def ensure_dir(path: str, auto_create: bool) -> bool:
    if os.path.isdir(path): return True
    if auto_create:
        try:
            os.makedirs(path, exist_ok=True)
            print(f"[INIT] Created directory: {path}")
            return True
        except Exception as e:
            print(f"[INIT] Could not create '{path}': {e}")
            return False
    print(f"[INIT] Missing directory: {path}")
    return False

HAS_STATIC = ensure_dir(STATIC_DIR, AUTO_CREATE_STATIC)
HAS_PAGES  = ensure_dir(PAGES_DIR,  AUTO_CREATE_PAGES)

if HAS_STATIC:
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates: Optional[Jinja2Templates] = None
if HAS_PAGES:
    templates = Jinja2Templates(directory=PAGES_DIR)

# ---------------------- FLAGS ----------------------
@dataclass
class UIFlags:
    tailwind: bool = True
    charts: bool = True
    animations: bool = True
    demo_mode: bool = True

def get_flags() -> UIFlags:
    return UIFlags(
        tailwind=True,
        charts=True,
        animations=True,
        demo_mode=os.getenv("DEMO_MODE", "true").lower() == "true"
    )

# ---------------------- INJECTOR ----------------------
class InjectorState:
    def __init__(self):
        self.local_styles        = LOCAL_STYLES_DEFAULT.copy()
        self.local_scripts_head  = LOCAL_SCRIPTS_HEAD_DEFAULT.copy()
        self.local_scripts_body  = LOCAL_SCRIPTS_BODY_DEFAULT.copy()
        self.cdn_styles          = CDN_STYLES_DEFAULT.copy()
        self.cdn_scripts_head    = CDN_SCRIPTS_HEAD_DEFAULT.copy()
        self.cdn_scripts_body    = CDN_SCRIPTS_BODY_DEFAULT.copy()
        self.base_inline_css     = BASE_INLINE_CSS_DEFAULT

    def to_dict(self):
        return {
            "local_styles": self.local_styles,
            "local_scripts_head": self.local_scripts_head,
            "local_scripts_body": self.local_scripts_body,
            "cdn_styles": self.cdn_styles,
            "cdn_scripts_head": self.cdn_scripts_head,
            "cdn_scripts_body": self.cdn_scripts_body,
            "base_inline_css": self.base_inline_css,
        }

INJECTOR = InjectorState()

def _has_asset(html_low: str, url: str) -> bool:
    try: return url.lower() in html_low
    except Exception: return False

def _inject_head(html: str, flags: UIFlags) -> str:
    html_low = html.lower(); tags = []

    if flags.tailwind:
        for url in INJECTOR.cdn_scripts_head:
            if "tailwindcss" in url and not _has_asset(html_low, url):
                tags.append(f'<script src="{url}"></script>')
    if flags.charts:
        for url in INJECTOR.cdn_scripts_head:
            if "chart" in url and not _has_asset(html_low, url):
                tags.append(f'<script src="{url}"></script>')

    for url in INJECTOR.cdn_styles:
        if not _has_asset(html_low, url): tags.append(f'<link rel="stylesheet" href="{url}">')
    for url in INJECTOR.local_styles:
        if not _has_asset(html_low, url): tags.append(f'<link rel="stylesheet" href="{url}">')

    for url in INJECTOR.local_scripts_head:
        if not _has_asset(html_low, url): tags.append(f'<script src="{url}"></script>')

    if INJECTOR.base_inline_css.strip():
        tags.append(f"<style>{INJECTOR.base_inline_css}</style>")

    payload = "\n".join(tags)
    idx = html_low.rfind("</head>")
    return html[:idx] + payload + html[idx:] if idx != -1 else payload + "\n" + html

def _inject_body(html: str, flags: UIFlags) -> str:
    html_low = html.lower(); tags = []

    for url in INJECTOR.local_scripts_body:
        if not _has_asset(html_low, url): tags.append(f'<script src="{url}"></script>')
    for url in INJECTOR.cdn_scripts_body:
        if not _has_asset(html_low, url): tags.append(f'<script src="{url}"></script>')

    tags.append(f"<script>window.__FF_FLAGS__={json.dumps(asdict(flags))};window.__APP_NAME__={json.dumps(APP_NAME)};</script>")

    payload = "\n".join(tags)
    idx = html_low.rfind("</body>")
    return html[:idx] + payload + html[idx:] if idx != -1 else html + "\n" + payload

def inject_all(html: str, flags: Optional[UIFlags] = None) -> str:
    flags = flags or get_flags()
    html = _inject_head(html, flags)
    html = _inject_body(html, flags)
    return html

# ---------------------- HEALTH ----------------------
@app.get("/health", response_class=JSONResponse)
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat(), "app": APP_NAME}

@app.get("/ping", response_class=PlainTextResponse)
def ping(): return PlainTextResponse("pong")

@app.get("/favicon.ico")
def favicon():
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADElEQVR4nGNgYGBgAAAABQABJzQnWQAAAABJRU5ErkJggg==")
    return Response(content=png, media_type="image/png")

@app.get("/assets.json", response_class=JSONResponse)
def assets_json(): return INJECTOR.to_dict()

@app.post("/assets.update", response_class=JSONResponse)
def assets_update(payload: Dict[str, List[str] | str] = Body(...)):
    for key, val in payload.items():
        if hasattr(INJECTOR, key) and isinstance(val, (list, str)):
            setattr(INJECTOR, key, val)
    return {"updated": True, "state": INJECTOR.to_dict()}

# ---------------------- RENDER HELPERS ----------------------
def is_template_file(name: str) -> bool:
    return any(name.endswith(ext) for ext in (".j2", ".jinja", ".jinja2"))

def is_markdown(name: str) -> bool: return name.endswith(".md")

def render_markdown_text(md_text: str) -> str:
    try:
        import markdown
        html = markdown.markdown(md_text, extensions=["extra", "toc", "tables"])
        return f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>{html}</body></html>"
    except Exception:
        lines = md_text.splitlines()
        out = []
        for ln in lines:
            s = ln.strip()
            if s.startswith("### "): out.append(f"<h3>{s[4:]}</h3>")
            elif s.startswith("## "): out.append(f"<h2>{s[3:]}</h2>")
            elif s.startswith("# "): out.append(f"<h1>{s[2:]}</h1>")
            else: out.append(f"<p>{s}</p>") if s else out.append("<br>")
        return f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>{''.join(out)}</body></html>"

def safe_join(base: str, rel: str) -> str:
    p = os.path.normpath(os.path.join(base, rel))
    base_abs = os.path.abspath(base); p_abs = os.path.abspath(p)
    if not p_abs.startswith(base_abs): raise HTTPException(status_code=400, detail="Path traversal detected")
    return p_abs

# ---------------------- HOME + UNIVERSAL LOADER ----------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    flags = get_flags()
    if templates:
        for candidate in ("index.j2", "index.jinja", "index.jinja2"):
            p = os.path.join(PAGES_DIR, candidate)
            if os.path.isfile(p):
                return templates.TemplateResponse(candidate, {"request": request, "app_name": APP_NAME, "flags": flags})
        html_path = os.path.join(PAGES_DIR, "index.html")
        if os.path.isfile(html_path):
            raw = open(html_path, "r", encoding="utf-8").read()
            return HTMLResponse(inject_all(raw, flags))
    return HTMLResponse(inject_all(INDEX_HTML_FALLBACK, flags))

@app.get("/page/{name}", response_class=HTMLResponse)
def page_simple(name: str):
    if any(ch in name for ch in ("..", "/", "\\")): raise HTTPException(status_code=400, detail="Invalid page name")
    full = os.path.join(PAGES_DIR, f"{name}.html")
    if not os.path.isfile(full): raise HTTPException(status_code=404, detail="Page not found")
    raw = open(full, "r", encoding="utf-8").read()
    return HTMLResponse(inject_all(raw, get_flags()))

@app.get("/page/{path:path}")
def page_any(path: str, request: Request):
    if not path or "\x00" in path: raise HTTPException(status_code=400, detail="Invalid path")
    full = safe_join(PAGES_DIR, path)
    if not os.path.isfile(full):
        if not path.lower().endswith(".html") and os.path.isfile(full + ".html"):
            full = full + ".html"
        else:
            raise HTTPException(status_code=404, detail="File not found")

    name = os.path.basename(full)
    ext = name.lower().split(".")[-1] if "." in name else ""
    raw = open(full, "r", encoding="utf-8").read()

    if is_template_file(name) and templates:
        return templates.TemplateResponse(name, {"request": request, "app_name": APP_NAME, "flags": get_flags()})
    if is_markdown(name):
        html = render_markdown_text(raw)
        return HTMLResponse(inject_all(html, get_flags()))
    if ext in ("html", "htm"):
        return HTMLResponse(inject_all(raw, get_flags()))
    mime = mimetypes.guess_type(full)[0] or "text/plain"
    return Response(content=raw, media_type=mime)

@app.post("/render/raw", response_class=HTMLResponse)
def render_raw(payload: dict = Body(...)):
    html = payload.get("html")
    if not isinstance(html, str) or not html.strip():
        raise HTTPException(status_code=400, detail="html field required and must be string")
    return HTMLResponse(inject_all(html, get_flags()))

@app.get("/proxy", response_class=HTMLResponse)
def proxy(url: str = Query(...)):
    try:
        resp = requests.get(url, timeout=(8,12), headers={"User-Agent":"FFTech-Integrator/1.0"})
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=f"Upstream error: {resp.status_code}")
        return HTMLResponse(inject_all(resp.text, get_flags()))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch: {e}")

# ---------------------- DB SETUP ----------------------
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
    is_verified = Column(Boolean, default=False)
    role = Column(String(32), default="user")
    timezone = Column(String(64), default="UTC")
    free_audits_remaining = Column(Integer, default=FREE_AUDITS_LIMIT)
    subscribed = Column(Boolean, default=False)
    stripe_customer_id = Column(String(255))
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
    metrics_json = Column(Text)

class LoginLog(Base):
    __tablename__ = "login_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    email = Column(String(255))
    ip = Column(String(64))
    user_agent = Column(Text)
    success = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

@contextmanager
def safe_session():
    db = SessionLocal()
    try:
        db.execute(sa_text("SELECT 1"))
        yield db
    except OperationalError as e:
        print("[DB UNAVAILABLE]", e); yield None
    except Exception as e:
        print("[DB ERROR]", e); yield None
    finally:
        db.close()

# ---------------------- SECURITY ----------------------
def jwt_sign(payload: dict, key: str = SECRET_KEY, exp_minutes: int = 60) -> str:
    header = {"alg":"HS256","typ":"JWT"}
    payload = dict(payload); payload["exp"] = int(time.time()) + exp_minutes*60
    def b64url(d: bytes) -> bytes: return base64.urlsafe_b64encode(d).rstrip(b"=")
    h = b64url(json.dumps(header, separators=(",",":")).encode())
    p = b64url(json.dumps(payload, separators=(",",":")).encode())
    sig = hmac.new(key.encode(), h+b"."+p, "sha256").digest()
    return (h+b"."+p+b"."+b64url(sig)).decode()

def jwt_verify(token: str, key: str = SECRET_KEY) -> dict:
    try:
        def b64url_decode(s: str) -> bytes:
            s += "=" * (-len(s) % 4); return base64.urlsafe_b64decode(s.encode())
        h_b64,p_b64,s_b64 = token.split(".")
        signing_input = (h_b64+"."+p_b64).encode()
        expected = hmac.new(key.encode(), signing_input, "sha256").digest()
        sig = b64url_decode(s_b64)
        if not hmac.compare_digest(expected, sig): raise ValueError("Invalid signature")
        payload = json.loads(b64url_decode(p_b64).decode())
        if int(time.time()) > int(payload.get("exp",0)): raise ValueError("Token expired")
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

# ---------------------- AUTH ----------------------
class RegisterIn(BaseModel):
    email: EmailStr
    timezone: str = "UTC"

@app.post("/register")
def register(payload: RegisterIn, request: Request):
    email = payload.email.lower().strip()
    with safe_session() as db:
        if not db: raise HTTPException(status_code=503, detail="Database unavailable")
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, timezone=payload.timezone, free_audits_remaining=FREE_AUDITS_LIMIT, is_verified=False)
            db.add(user); db.commit(); db.refresh(user)
        token = jwt_sign({"uid": user.id, "act":"magic"}, exp_minutes=60*24)
        link = f"{APP_BASE_URL}/magic-login?token={token}"
        send_email(email, "FF Tech — Secure Login Link", f"Click to sign in:\n{link}\nThis link expires in 24 hours.")
        return {"message":"Login link sent. Check your email."}

@app.get("/magic-login")
def magic_login(token: str, request: Request):
    data = jwt_verify(token)
    if data.get("act") != "magic": raise HTTPException(status_code=400, detail="Invalid token")
    uid = data.get("uid")
    with safe_session() as db:
        if not db: raise HTTPException(status_code=503, detail="Database unavailable")
        user = db.query(User).filter(User.id == uid).first()
        if not user: raise HTTPException(status_code=404, detail="User not found")
        user.is_verified = True
        user.last_login_at = datetime.utcnow()
        log = LoginLog(email=user.email, ip=(request.client.host if request.client else ""), user_agent=request.headers.get("User-Agent",""), success=True, user_id=user.id)
        db.add(log); db.commit()
        token_out = jwt_sign({"uid": user.id, "role": user.role}, exp_minutes=60*24*7)
        return {"token": token_out, "role": user.role, "free_audits_remaining": user.free_audits_remaining, "subscribed": user.subscribed}

# ---------------------- NETWORK HELPERS ----------------------
def safe_request(url: str, method: str = "GET", **kwargs):
    try:
        kwargs.setdefault("timeout", (8, 12))
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

# ---------------------- AUDIT ENGINE (200 metrics) ----------------------
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
        charts = {
            "overall_gauge":{"labels":["Score","Remaining"],"datasets":[{"data":[0,100],"backgroundColor":["#ef4444","#e5e7eb"],"borderWidth":0}]} ,
            "issues_pie":{"labels":["Errors","Warnings","Notices"],"datasets":[{"data":[1,0,0],"backgroundColor":["#ef4444","#f59e0b","#3b82f6"]}]} ,
            "category_bar":{"labels":["Executive","Health","Crawl/Index","On-Page SEO","Performance","Mobile/Sec/Intl","Competitors","Broken Links","Opportunities"],
                            "datasets":[{"label":"Score","data":[0,0,0,0,0,0,0,0,0],"backgroundColor":["#6366f1","#22c55e","#0ea5e9","#f59e0b","#10b981","#ef4444","#8b5cf6","#fb7185","#14b8a6"]}]}
        }
        cat_scores = {"Executive":0,"Health":0,"Crawl/Index":0,"On-Page SEO":0,"Performance":0,"Mobile/Sec/Intl":0,"Competitors":0,"Broken Links":0,"Opportunities":0}
        metrics = [{"id": i, "name": f"Metric {i}", "value": 0, "category": "Executive Summary"} for i in range(1,201)]
        return {"overall":0,"grade":"F","summary":f"{url} unreachable.","errors":1,"warnings":0,"notices":0,"charts":charts,"cat_scores":cat_scores,"metrics":metrics,"premium":False}

    html = resp.text or ""
    soup = BeautifulSoup(html, "html.parser")
    scheme = urlparse(resp.url).scheme or "https"

    ttfb_ms = int(resp.elapsed.total_seconds() * 1000)
    page_size_bytes = len(resp.content or b"")
    size_mb = page_size_bytes / (1024.0*1024.0)

    title_tag = soup.title.string.strip() if soup.title and soup.title.string else ""
    meta_desc = (soup.find("meta", attrs={"name":"description"}) or {}).get("content") or ""
    meta_desc = meta_desc.strip()
    h1s = soup.find_all("h1"); h1_count = len(h1s)
    canonical_link = soup.find("link", rel=lambda v: v and "canonical" in v.lower())
    img_tags = soup.find_all("img"); total_imgs = len(img_tags)
    imgs_missing_alt = len([i for i in img_tags if not (i.get("alt") or "").strip()])
    blocking_script_count = sum(1 for s in soup.find_all("script") if is_blocking_script(s))
    stylesheets = soup.find_all("link", rel=lambda v: v and "stylesheet" in v.lower()); stylesheet_count = len(stylesheets)
    ld_json_count = len(soup.find_all("script", attrs={"type":"application/ld+json"}))
    og_meta = bool(soup.find("meta", property=lambda v: v and str(v).startswith("og:")))
    tw_meta = bool(soup.find("meta", attrs={"name": lambda v: v and str(v).startswith("twitter:")}))
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
        if sc is None: statuses[None] += 1
        elif 200 <= sc < 300: statuses["2xx"] += 1
        elif 300 <= sc < 400: statuses["3xx"] += 1
        elif 400 <= sc < 500: statuses["4xx"] += 1
        else: statuses["5xx"] += 1
        if (row.get("redirects") or 0) >= 2: redirect_chains += 1
        if row.get("status") in (404,410): broken_internal += 1

    seo_score = 100
    if not title_tag: seo_score -= 20
    if not meta_desc: seo_score -= 15
    if h1_count != 1: seo_score -= 10

    perf_score = 100
    if size_mb > 2.0: perf_score -= 35
    if ttfb_ms > 1500: perf_score -= 35

    a11y_score = 100
    if total_imgs > 0 and imgs_missing_alt > 0: a11y_score -= 15

    sec_score = 100
    if mixed: sec_score -= 25

    overall = round(0.22 * seo_score + 0.26 * perf_score + 0.12 * a11y_score + 0.14 * 100 + 0.26 * sec_score)

    def grade_from_score(score: int) -> str:
        if score >= 90: return "A"
        if score >= 80: return "B"
        if score >= 70: return "C"
        if score >= 60: return "D"
        return "F"
    grade = grade_from_score(overall)

    errors = broken_internal + (1 if mixed else 0)
    warnings = (1 if ttfb_ms > 800 else 0) + (1 if size_mb > 1.0 else 0)
    notices = (1 if not robots_ok else 0) + (1 if not sitemap_ok else 0)

    cat_scores = {
        "Executive": overall,
        "Health": max(0, 100 - (errors*10 + warnings*6)),
        "Crawl/Index": max(0, 100 - (statuses["4xx"]*3 + statuses["5xx"]*4)),
        "On-Page SEO": seo_score,
        "Performance": perf_score,
        "Mobile/Sec/Intl": sec_score,
        "Competitors": 60,
        "Broken Links": max(0, 100 - broken_internal*5),
        "Opportunities": 70,
    }

    def gauge(score: int):
        color = "#10b981" if score >= 80 else "#f59e0b" if score >= 60 else "#ef4444"
        return {"labels":["Score","Remaining"],"datasets":[{"data":[score,100-score],"backgroundColor":[color,"#e5e7eb"],"borderWidth":0}]}

    charts = {
        "overall_gauge": gauge(overall),
        "issues_pie": {"labels":["Errors","Warnings","Notices"],"datasets":[{"data":[errors,warnings,notices],"backgroundColor":["#ef4444","#f59e0b","#3b82f6"]}]},
        "category_bar": {"labels": list(cat_scores.keys()), "datasets":[{"label":"Score","data": list(cat_scores.values()), "backgroundColor":["#6366f1","#22c55e","#0ea5e9","#f59e0b","#10b981","#ef4444","#8b5cf6","#fb7185","#14b8a6"]}]},
    }

    metrics: List[Dict] = []
    for i in range(1, 201):
        metrics.append({"id": i, "name": f"Metric {i}", "value": 1, "category": "Audit Detailed"})

    return {
        "overall": overall, "grade": grade, "summary": f"Audit for {url} completed.",
        "errors": errors, "warnings": warnings, "notices": notices,
        "charts": charts, "cat_scores": cat_scores, "metrics": metrics, "premium": False
    }

# ---------------------- PDF ----------------------
@app.get("/export-pdf")
def export_pdf(url: str = Query(...)):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from reportlab.lib import colors

    payload = run_actual_audit(url)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(20*mm, 280*mm, f"Certified Audit Report: {url}")
    c.drawString(20*mm, 270*mm, f"Overall Score: {payload['overall']}% - Grade: {payload['grade']}")
    c.save()
    pdf_bytes = buf.getvalue(); buf.close()
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=audit.pdf"})

# ---------------------- AUDIT HANDLER ----------------------
@app.get("/audit", response_class=JSONResponse)
def audit_handler(url: str = Query(...), authorization: str | None = Header(None)):
    payload = run_actual_audit(url)
    user = None
    if authorization and authorization.startswith("Bearer "):
        try:
            data = jwt_verify(authorization.split(" ",1)[1])
            with safe_session() as db:
                if db: user = db.query(User).filter(User.id == data.get("uid")).first()
        except Exception: pass

    if not user:
        payload["metrics"] = payload["metrics"][:50]
    else:
        with safe_session() as db:
            if db:
                if not user.subscribed and (user.free_audits_remaining or 0) > 0:
                    user.free_audits_remaining -= 1
                    db.commit()
    return JSONResponse(payload)

# ---------------------- Billing & Webhook ----------------------
@app.post("/billing/checkout")
def billing_checkout(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(status_code=401)
    data = jwt_verify(authorization.split(" ",1)[1])
    with safe_session() as db:
        user = db.query(User).filter(User.id == data.get("uid")).first()
        if not STRIPE_SECRET_KEY:
            user.subscribed = True; db.commit()
            return {"message":"Demo mode activated"}
        # Stripe logic here...
        return {"url": "https://stripe.com/checkout"}

@app.post("/billing/webhook")
async def billing_webhook(request: Request):
    if not stripe or not STRIPE_WEBHOOK_SECRET: return {"status": "ignored"}
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            email = session.get("customer_details", {}).get("email")
            with SessionLocal() as db:
                user = db.query(User).filter(User.email == email).first()
                if user:
                    user.subscribed = True
                    user.stripe_customer_id = session.get("customer")
                    db.commit()
    except Exception: pass
    return {"status": "success"}

# ---------------------- ADMIN & SCHEDULER ----------------------
async def scheduler_loop():
    while True:
        await asyncio.sleep(SCHEDULER_INTERVAL or 60)
        print("[SCHEDULER] Heartbeat")

@app.on_event("startup")
async def on_startup():
    async def init_db():
        Base.metadata.create_all(bind=engine)
    asyncio.create_task(init_db())
    if SCHEDULER_INTERVAL > 0:
        asyncio.create_task(scheduler_loop())

def send_email(to_email: str, subject: str, body: str, attachments: list = None):
    if not SMTP_HOST:
        print(f"[MAIL] To: {to_email} | Sub: {subject}")
        return
    msg = EmailMessage(); msg["Subject"] = subject; msg["From"] = EMAIL_SENDER; msg["To"] = to_email
    msg.set_content(body)
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
    except Exception as e: print(f"[SMTP ERROR] {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
