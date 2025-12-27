
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

import os, io, hmac, json, time, base64, secrets, asyncio, mimetypes
from dataclasses import dataclass, asdict
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
from typing import Optional, List, Dict

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

    # CDN scripts (head)
    if flags.tailwind:
        for url in INJECTOR.cdn_scripts_head:
            if "tailwindcss" in url and not _has_asset(html_low, url):
                tags.append(f'{url}</script>')
    if flags.charts:
        for url in INJECTOR.cdn_scripts_head:
            if "chart" in url and not _has_asset(html_low, url):
                tags.append(f'{url}</script>')

    # Styles
    for url in INJECTOR.cdn_styles:
        if not _has_asset(html_low, url): tags.append(f'{url}')
    for url in INJECTOR.local_styles:
        if not _has_asset(html_low, url): tags.append(f'{url}')

    # Local head scripts
    for url in INJECTOR.local_scripts_head:
        if not _has_asset(html_low, url): tags.append(f'{url}</script>')

    # Inline CSS
    if INJECTOR.base_inline_css.strip():
        tags.append(f"<style>{INJECTOR.base_inline_css}</style>")

    payload = "\n".join(tags)
    idx = html_low.rfind("</head>")
    return html[:idx] + payload + html[idx:] if idx != -1 else payload + "\n" + html

def _inject_body(html: str, flags: UIFlags) -> str:
    html_low = html.lower(); tags = []

    # Local body scripts
    for url in INJECTOR.local_scripts_body:
        if not _has_asset(html_low, url): tags.append(f'{url}</script>')

    # CDN body scripts (optional)
    for url in INJECTOR.cdn_scripts_body:
        if not _has_asset(html_low, url): tags.append(f'{url}</script>')

    # Flags bootstrap
    tags.append(f"<script>window.__FF_FLAGS__={json.dumps(asdict(flags))};window.__APP_NAME__={json.dumps(APP_NAME)};</script>")

    payload = "\n".join(tags)
    idx = html_low.rfind("</body>")
    return html[:idx] + payload + html[idx:] if idx != -1 else html + "\n" + payload

def inject_all(html: str, flags: Optional[UIFlags] = None) -> str:
    flags = flags or get_flags()
    html = _inject_head(html, flags)
    html = _inject_body(html, flags)
    return html

# ---------------------- HEALTH (FIXED: instant 200 OK) ----------------------
@app.get("/health", response_class=JSONResponse)
def health():
    # Independent of DB or external services; returns 200 immediately.
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
    cat_scores_json = Column(Text)   # per-category scores
    metrics_json = Column(Text)      # 200 metrics payload

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
    db = None
    try:
        db = SessionLocal()
        db.execute(sa_text("SELECT 1"))
        yield db
    except OperationalError as e:
        print("[DB UNAVAILABLE]", e); yield None
    except Exception as e:
        print("[DB ERROR]", e); yield None
    finally:
        try:
            if db: db.close()
        except Exception: pass

# ---------------------- SECURITY (magic link + JWT) ----------------------
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
        # 24h magic login link
        token = jwt_sign({"uid": user.id, "act":"magic"}, exp_minutes=60*24)
        link = f"{APP_BASE_URL}/magic-login?token={token}"
        subj = "FF Tech — Secure Login Link"
        body = f"Click to sign in:\n{link}\nThis link expires in 24 hours."
        send_email(email, subj, body, [])
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
        # Long-lived JWT
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

# ---------------------- AUDIT ENGINE (200 metrics grouped) ----------------------
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

    # Unreachable: full structure with zeros/placeholders
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

    # Measures
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

    # Scoring heuristics
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

    overall = round(0.22 * seo_score + 0.26 * perf_score + 0.12 * a11y_score + 0.14 * bp_score + 0.26 * sec_score)

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

    # Category scores
    cat_scores = {
        "Executive": overall,
        "Health": max(0, 100 - (errors*10 + warnings*6)),
        "Crawl/Index": max(0, 100 - (statuses["4xx"]*3 + statuses["5xx"]*4 + redirect_chains*2 + broken_internal*3)),
        "On-Page SEO": seo_score,
        "Performance": perf_score,
        "Mobile/Sec/Intl": int(0.5*sec_score + 0.5*(85 if viewport_meta else 60)),
        "Competitors": 60,   # placeholder
        "Broken Links": max(0, 100 - broken_internal*5),
        "Opportunities": 70, # placeholder
    }

    exec_summary = (
        f"FF Tech audited {resp.url}. Overall health {overall}% (grade {grade}). "
        f"Payload {size_mb:.2f} MB; TTFB {ttfb_ms} ms. Improve SEO (H1/meta/canonical/alt/JSON-LD), "
        f"add security headers (HSTS/CSP/XFO/XCTO/Referrer-Policy), and fix broken links."
    )

    def gauge(score: int, color_good="#10b981"):
        color = color_good if score >= 80 else "#f59e0b" if score >= 60 else "#ef4444"
        return {"labels":["Score","Remaining"],"datasets":[{"data":[score,100-score],"backgroundColor":[color,"#e5e7eb"],"borderWidth":0}]}

    charts = {
        "overall_gauge": gauge(overall),
        "issues_pie": {"labels":["Errors","Warnings","Notices"],
                       "datasets":[{"data":[errors,warnings,notices],
                                    "backgroundColor":["#ef4444","#f59e0b","#3b82f6"]}]},
        "category_bar": {"labels": list(cat_scores.keys()),
                         "datasets":[{"label":"Score","data": list(cat_scores.values()),
                                      "backgroundColor":["#6366f1","#22c55e","#0ea5e9","#f59e0b","#10b981","#ef4444","#8b5cf6","#fb7185","#14b8a6"]}]},
    }

    metrics: List[Dict] = []
    def add_metrics(start_id: int, items: List[tuple], category: str):
        for idx,(name,val) in enumerate(items, start=start_id):
            metrics.append({"id": idx, "name": name, "value": val, "category": category})

    # A. Executive (1–10)
    add_metrics(1, [
        ("Overall Site Health Score (%)", overall),
        ("Website Grade (A+ to D)", grade),
        ("Executive Summary (200 Words)", 1),
        ("Strengths Highlight Panel", 1),
        ("Weak Areas Highlight Panel", 1),
        ("Priority Fixes Panel", 1),
        ("Visual Severity Indicators", errors + warnings + notices),
        ("Category Score Breakdown", 1),
        ("Industry-Standard Presentation", 1),
        ("Print / Certified Export Readiness", 1),
    ], "Executive Summary")

    # B. Health (11–20)
    add_metrics(11, [
        ("Site Health Score", cat_scores["Health"]),
        ("Total Errors", errors),
        ("Total Warnings", warnings),
        ("Total Notices", notices),
        ("Total Crawled Pages", len(crawled)),
        ("Total Indexed Pages", None),
        ("Issues Trend", None),
        ("Crawl Budget Efficiency", None),
        ("Orphan Pages Percentage", None),
        ("Audit Completion Status", 1),
    ], "Overall Site Health")

    # C. Crawl & Index (21–40)
    add_metrics(21, [
        ("HTTP 2xx Pages", statuses["2xx"]),
        ("HTTP 3xx Pages", statuses["3xx"]),
        ("HTTP 4xx Pages", statuses["4xx"]),
        ("HTTP 5xx Pages", statuses["5xx"]),
        ("Redirect Chains", redirect_chains),
        ("Redirect Loops", None),
        ("Broken Internal Links", broken_internal),
        ("Broken External Links", None),
        ("robots.txt Blocked URLs", None),
        ("Meta Robots Blocked URLs", None),
        ("Non-Canonical Pages", None),
        ("Missing Canonical Tags", 0 if canonical_link else 1),
        ("Incorrect Canonical Tags", None),
        ("Sitemap Missing Pages", None),
        ("Sitemap Not Crawled Pages", None),
        ("Hreflang Errors", None),
        ("Hreflang Conflicts", None),
        ("Pagination Issues", None),
        ("Crawl Depth Distribution", None),
        ("Duplicate Parameter URLs", None),
    ], "Crawlability & Indexation")

    # D. On-Page SEO (41–75)
    add_metrics(41, [
        ("Missing Title Tags", 0 if title_tag else 1),
        ("Duplicate Title Tags", None),
        ("Title Too Long", 1 if title_tag and len(title_tag)>65 else 0),
        ("Title Too Short", 1 if title_tag and len(title_tag)<10 else 0),
        ("Missing Meta Descriptions", 0 if meta_desc else 1),
        ("Duplicate Meta Descriptions", None),
        ("Meta Too Long", 1 if meta_desc and len(meta_desc)>165 else 0),
        ("Meta Too Short", 1 if meta_desc and len(meta_desc)<50 else 0),
        ("Missing H1", 1 if h1_count==0 else 0),
        ("Multiple H1", 1 if h1_count>1 else 0),
        ("Duplicate Headings", None),
        ("Thin Content Pages", None),
        ("Duplicate Content Pages", None),
        ("Low Text-to-HTML Ratio", None),
        ("Missing Image Alt Tags", imgs_missing_alt),
        ("Duplicate Alt Tags", None),
        ("Large Uncompressed Images", None),
        ("Pages Without Indexed Content", None),
        ("Missing Structured Data", 1 if ld_json_count==0 else 0),
        ("Structured Data Errors", None),
        ("Rich Snippet Warnings", None),
        ("Missing Open Graph Tags", 0 if og_meta else 1),
        ("Long URLs", None),
        ("Uppercase URLs", None),
        ("Non-SEO-Friendly URLs", None),
        ("Too Many Internal Links", None),
        ("Pages Without Incoming Links", None),
        ("Orphan Pages", None),
        ("Broken Anchor Links", None),
        ("Redirected Internal Links", None),
        ("NoFollow Internal Links", None),
        ("Link Depth Issues", None),
        ("External Links Count", None),
        ("Broken External Links", None),
        ("Anchor Text Issues", None),
    ], "On-Page SEO")

    # E. Performance & Technical (76–96)
    add_metrics(76, [
        ("Largest Contentful Paint (LCP)", None),
        ("First Contentful Paint (FCP)", None),
        ("Cumulative Layout Shift (CLS)", None),
        ("Total Blocking Time", None),
        ("First Input Delay", None),
        ("Speed Index", None),
        ("Time to Interactive", None),
        ("DOM Content Loaded", None),
        ("Total Page Size (MB)", round(size_mb,2)),
        ("Requests Per Page", None),
        ("Unminified CSS", None),
        ("Unminified JavaScript", None),
        ("Render Blocking Resources", blocking_script_count),
        ("Excessive DOM Size", None),
        ("Third-Party Script Load", None),
        ("Server Response Time (ms)", ttfb_ms),
        ("Image Optimization", None),
        ("Lazy Loading Issues", None),
        ("Browser Caching Issues", None),
        ("Missing GZIP / Brotli", None),
        ("Resource Load Errors", None),
    ], "Performance & Technical")

    # F. Mobile, Security & International (97–150)
    add_metrics(97, [
        ("Mobile Friendly Test", None),
        ("Viewport Meta Tag", 1 if viewport_meta else 0),
        ("Small Font Issues", None),
        ("Tap Target Issues", None),
        ("Mobile Core Web Vitals", None),
        ("Mobile Layout Issues", None),
        ("Intrusive Interstitials", None),
        ("Mobile Navigation Issues", None),
        ("HTTPS Implementation", 1 if scheme=="https" else 0),
        ("SSL Certificate Validity", None),
        ("Expired SSL", None),
        ("Mixed Content", 1 if mixed else 0),
        ("Insecure Resources", 1 if mixed else 0),
        ("Missing Security Headers", 1 if not headers.get("Content-Security-Policy") else 0),
        ("Open Directory Listing", None),
        ("Login Pages Without HTTPS", None),
        ("Missing Hreflang", None),
        ("Incorrect Language Codes", None),
        ("Hreflang Conflicts", None),
        ("Region Targeting Issues", None),
        ("Multi-Domain SEO Issues", None),
        ("Domain Authority", None),
        ("Referring Domains", None),
        ("Total Backlinks", None),
        ("Toxic Backlinks", None),
        ("NoFollow Backlinks", None),
        ("Anchor Distribution", None),
        ("Referring IPs", None),
        ("Lost / New Backlinks", None),
        ("JavaScript Rendering Issues", None),
        ("CSS Blocking", None),
        ("Crawl Budget Waste", None),
        ("AMP Issues", None),
        ("PWA Issues", None),
        ("Canonical Conflicts", None),
        ("Subdomain Duplication", None),
        ("Pagination Conflicts", None),
        ("Dynamic URL Issues", None),
        ("Lazy Load Conflicts", None),
        ("Sitemap Presence", 1 if sitemap_ok else 0),
        ("Noindex Issues", None),
        ("Structured Data Consistency", None),
        ("Redirect Correctness", None),
        ("Broken Rich Media", None),
        ("Social Metadata Presence", 1 if (og_meta or tw_meta) else 0),
        ("Error Trend", None),
        ("Health Trend", None),
        ("Crawl Trend", None),
        ("Index Trend", None),
        ("Core Web Vitals Trend", None),
        ("Backlink Trend", None),
        ("Keyword Trend", None),
        ("Historical Comparison", None),
        ("Overall Stability Index", None),
    ], "Mobile, Security & International")

    # G. Competitor Analysis (151–167) placeholders
    comp_names = [
        "Competitor Health Score","Competitor Performance Comparison","Competitor Core Web Vitals Comparison",
        "Competitor SEO Issues Comparison","Competitor Broken Links Comparison","Competitor Authority Score",
        "Competitor Backlink Growth","Competitor Keyword Visibility","Competitor Rank Distribution",
        "Competitor Content Volume","Competitor Speed Comparison","Competitor Mobile Score",
        "Competitor Security Score","Competitive Gap Score","Competitive Opportunity Heatmap",
        "Competitive Risk Heatmap","Overall Competitive Rank"
    ]
    add_metrics(151, [(nm, None) for nm in comp_names], "Competitor Analysis")

    # H. Broken Links Intelligence (168–180)
    add_metrics(168, [
        ("Total Broken Links", broken_internal),
        ("Internal Broken Links", broken_internal),
        ("External Broken Links", None),
        ("Broken Links Trend", None),
        ("Broken Pages by Impact", None),
        ("Status Code Distribution", None),
        ("Page Type Distribution", None),
        ("Fix Priority Score", None),
        ("SEO Loss Impact", None),
        ("Affected Pages Count", None),
        ("Broken Media Links", None),
        ("Resolution Progress", None),
        ("Risk Severity Index", None),
    ], "Broken Links Intelligence")

    # I. Opportunities, Growth & ROI (181–200)
    opp_names = [
        "High Impact Opportunities","Quick Wins Score","Long-Term Fixes","Traffic Growth Forecast","Ranking Growth Forecast",
        "Conversion Impact Score","Content Expansion Opportunities","Internal Linking Opportunities","Speed Improvement Potential",
        "Mobile Improvement Potential","Security Improvement Potential","Structured Data Opportunities","Crawl Optimization Potential",
        "Backlink Opportunity Score","Competitive Gap ROI","Fix Roadmap Timeline","Time-to-Fix Estimate","Cost-to-Fix Estimate",
        "ROI Forecast","Overall Growth Readiness"
    ]
    add_metrics(181, [(nm, None) for nm in opp_names], "Opportunities, Growth & ROI")

    return {
        "overall": overall,
        "grade": grade,
        "summary": exec_summary,
        "errors": errors, "warnings": warnings, "notices": notices,
        "charts": charts,
        "cat_scores": cat_scores,
        "metrics": metrics,
        "premium": False,   # set per user in handler
    }

# ---------------------- PDF (5 pages, charts & branding) ----------------------
@app.get("/export-pdf")
def export_pdf(url: str = Query(...)):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics import renderPDF

    payload = run_actual_audit(url)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    def header_footer(page_title: str):
        c.setFillColor(colors.indigo); c.rect(0, H-35*mm, W, 35*mm, fill=True, stroke=False)
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 16)
        c.drawString(20*mm, H-20*mm, APP_NAME)
        c.setFont("Helvetica", 10); c.drawRightString(W-20*mm, H-20*mm, datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
        c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 18)
        c.drawString(20*mm, H-45*mm, page_title)
        c.setFont("Helvetica", 9); c.setFillColor(colors.slategray)
        c.drawString(20*mm, 12*mm, "© FF Tech — Certified Website Audit • support@fftech.io")

    # Page 1: cover
    header_footer("Certified Audit Report")
    c.setFont("Helvetica-Bold", 24); c.setFillColor(colors.indigo)
    c.drawString(20*mm, H-65*mm, "Executive Website Health")
    c.setFillColor(colors.black); c.setFont("Helvetica", 12)
    c.drawString(20*mm, H-80*mm, f"Website: {normalize_url(url)}")
    c.drawString(20*mm, H-90*mm, f"Grade: {payload['grade']}")
    c.drawString(20*mm, H-100*mm, f"Overall Score: {payload['overall']}%")
    c.showPage()

    # Page 2: gauges & issues
    header_footer("Score Gauge & Issues Breakdown")
    d1 = Drawing(180, 180)
    p1 = Pie(); p1.x = 40; p1.y = 20; p1.width = 100; p1.height = 100
    p1.data = [payload["overall"], 100 - payload["overall"]]
    p1.labels = ["Score", "Remaining"]; p1.slices[0].fillColor = colors.Color(0.13,0.59,0.95); p1.slices[1].fillColor = colors.Color(0.90,0.92,0.95)
    d1.add(p1); d1.add(String(40, 130, "Overall Health", fontName="Helvetica-Bold", fontSize=12, fillColor=colors.indigo))
    renderPDF.draw(d1, c, 20*mm, H-180*mm)

    d2 = Drawing(220, 180)
    p2 = Pie(); p2.x = 60; p2.y = 20; p2.width = 100; p2.height = 100
    p2.data = [payload["errors"], payload["warnings"], payload["notices"]]
    p2.labels = ["Errors","Warnings","Notices"]
    p2.slices[0].fillColor = colors.Color(0.93,0.36,0.36); p2.slices[1].fillColor = colors.Color(0.96,0.62,0.12); p2.slices[2].fillColor = colors.Color(0.23,0.51,0.96)
    d2.add(p2); d2.add(String(40, 130, "Issues Breakdown", fontName="Helvetica-Bold", fontSize=12, fillColor=colors.indigo))
    renderPDF.draw(d2, c, 115*mm, H-180*mm)
    c.showPage()

    # Page 3: categories
    header_footer("Category Scores")
    labels = list(payload["cat_scores"].keys()); vals = list(payload["cat_scores"].values())
    d3 = Drawing(400, 220)
    bc = VerticalBarChart(); bc.x = 50; bc.y = 30; bc.height = 140; bc.width = 300
    bc.data = [vals]; bc.categoryAxis.categoryNames = labels
    bc.barWidth = 18; bc.groupSpacing = 12
    bc.valueAxis.valueMin = 0; bc.valueAxis.valueMax = 100; bc.valueAxis.valueStep = 20
    bc.bars[0].fillColor = colors.Color(0.39,0.33,0.94)
    d3.add(bc); d3.add(String(50, 180, "Executive / Health / Crawl / SEO / Performance / MSI / Competitors / Broken / Opportunities", fontName="Helvetica-Bold", fontSize=10, fillColor=colors.indigo))
    renderPDF.draw(d3, c, 20*mm, H-230*mm)
    c.showPage()

    # Page 4: narrative
    header_footer("Strengths, Weaknesses & Priorities")
    c.setFont("Helvetica", 11)
    summary = payload["summary"]; lines = []
    while summary:
        lines.append(summary[:95]); summary = summary[95:]
    y = H-70*mm
    c.setFont("Helvetica-Bold", 12); c.setFillColor(colors.indigo); c.drawString(20*mm, y, "Executive Summary"); y-=8*mm
    c.setFillColor(colors.black); c.setFont("Helvetica", 11)
    for ln in lines[:12]: c.drawString(25*mm, y, ln); y-=6*mm

    def bullets(title, items, color):
        nonlocal y
        c.setFont("Helvetica-Bold", 12); c.setFillColor(color); c.drawString(20*mm, y, title); y-=8*mm
        c.setFillColor(colors.black); c.setFont("Helvetica", 11)
        for it in (items[:8] if items else ["—"]): c.drawString(25*mm, y, f"• {it}"); y-=6*mm
        y-=4*mm

    bullets("Strengths", ["Security posture present (HTTPS/headers).","Mobile viewport present.","Foundational SEO elements."], colors.Color(0.10,0.64,0.47))
    bullets("Weaknesses", ["Render-blocking JS; heavy payload.","Missing/weak CSP.","Broken internal links."], colors.Color(0.93,0.36,0.36))
    bullets("Priority Fixes", ["Add HSTS/CSP/XFO/XCTO/Referrer-Policy.","Defer/async JS; inline critical CSS.","Compress images; enable caching."], colors.Color(0.39,0.33,0.94))
    c.showPage()

    # Page 5: signals
    header_footer("Top Signals Snapshot")
    top = payload["metrics"][:12]
    labels = [m["name"][:18] for m in top]
    passes = []
    for m in top:
        val = m.get("value")
        try:
            n = 100 if isinstance(val, str) else (int(val) if isinstance(val,(int,float)) else 50)
        except Exception:
            n = 50
        passes.append(max(0, min(100, n)))

    d5 = Drawing(400, 220)
    bc2 = VerticalBarChart(); bc2.x = 50; bc2.y = 30; bc2.height = 140; bc2.width = 300
    bc2.data = [passes]; bc2.categoryAxis.categoryNames = labels
    bc2.barWidth = 16; bc2.groupSpacing = 10
    bc2.valueAxis.valueMin = 0; bc2.valueAxis.valueMax = 100; bc2.valueAxis.valueStep = 20
    bc2.bars[0].fillColor = colors.Color(0.13,0.59,0.95)
    d5.add(bc2); d5.add(String(50, 180, "Signals Snapshot", fontName="Helvetica-Bold", fontSize=12, fillColor=colors.indigo))
    renderPDF.draw(d5, c, 20*mm, H-230*mm)

    c.save()
    pdf_bytes = buf.getvalue(); buf.close()
    fname = f"fftech_audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename=\"{fname}\"'})

# ---------------------- AUDIT HANDLER (Open vs Registered) ----------------------
@app.get("/audit", response_class=JSONResponse)
def audit_handler(url: str = Query(...), authorization: str | None = Header(None)):
    payload = run_actual_audit(url)
    user = None
    if authorization and authorization.startswith("Bearer "):
        try:
            data = jwt_verify(authorization.split(" ",1)[1])
            with safe_session() as db:
                if db: user = db.query(User).filter(User.id == data.get("uid")).first()
        except Exception: user = None

    # Access policy
    if not user:
        payload["metrics"] = payload["metrics"][:50]
        payload["premium"] = False
    else:
        with safe_session() as db:
            remaining = user.free_audits_remaining or 0
            is_subscribed = bool(user.subscribed)
            if not is_subscribed and remaining <= 0:
                payload["metrics"] = payload["metrics"][:50]
                payload["premium"] = False
            else:
                payload["premium"] = True
                if db and not is_subscribed and remaining > 0:
                    user.free_audits_remaining = max(0, remaining - 1); db.commit()

    # Persist audit
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
                metrics_json=json.dumps(payload.get("metrics", [])),
            )
            db.add(row); db.commit()

    return JSONResponse(payload)

# ---------------------- Websites & Scheduling ----------------------
class WebsiteIn(BaseModel): url: str
class ScheduleIn(BaseModel):
    website_url: str
    time_of_day: str
    timezone: str
    preferred_date: str | None = None
    enabled: bool = True

@app.post("/websites")
def add_website(payload: WebsiteIn, authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(status_code=401, detail="Authorization required")
    data = jwt_verify(authorization.split(" ",1)[1])
    with safe_session() as db:
        if not db: raise HTTPException(status_code=503, detail="Database unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        url = normalize_url(payload.url)
        existing = db.query(Website).filter(Website.url == url, Website.user_id == user.id).first()
        if existing: return {"message":"Website already added"}
        site = Website(url=url, user_id=user.id, active=True)
        db.add(site); db.commit(); db.refresh(site)
        return {"message":"Website added", "id": site.id}

@app.post("/schedule")
def create_schedule(payload: ScheduleIn, authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(status_code=401, detail="Authorization required")
    data = jwt_verify(authorization.split(" ",1)[1])
    with safe_session() as db:
        if not db: raise HTTPException(status_code=503, detail="Database unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        url = normalize_url(payload.website_url)
        site = db.query(Website).filter(Website.url == url, Website.user_id == user.id).first()
        if not site:
            site = Website(url=url, user_id=user.id, active=True)
            db.add(site); db.commit(); db.refresh(site)
        pref_dt = None
        if payload.preferred_date:
            try: pref_dt = datetime.fromisoformat(payload.preferred_date.strip())
            except Exception: raise HTTPException(status_code=400, detail="Invalid preferred_date format (ISO8601).")
        sched = Schedule(
            user_id=user.id, website_id=site.id, enabled=payload.enabled,
            time_of_day=payload.time_of_day, timezone=payload.timezone,
            preferred_date=pref_dt
        )
        db.add(sched); db.commit(); db.refresh(sched)
        return {"message":"Schedule saved", "id": sched.id}

@app.get("/schedules")
def list_schedules(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(status_code=401, detail="Authorization required")
    data = jwt_verify(authorization.split(" ",1)[1])
    with safe_session() as db:
        if not db: raise HTTPException(status_code=503, detail="Database unavailable")
        rows = db.query(Schedule).filter(Schedule.user_id == data.get("uid")).all()
        out = []
        for s in rows:
            site = db.get(Website, s.website_id) if hasattr(db, "get") else db.query(Website).get(s.website_id)
            out.append({"id": s.id, "website_url": site.url if site else None, "enabled": s.enabled,
                        "time_of_day": s.time_of_day, "timezone": s.timezone,
                        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None})
        return out

# ---------------------- Billing (Stripe or demo) ----------------------
@app.get("/billing/status")
def billing_status(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(status_code=401, detail="Authorization required")
    data = jwt_verify(authorization.split(" ",1)[1])
    with safe_session() as db:
        if not db: raise HTTPException(status_code=503, detail="Database unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        return {"subscribed": user.subscribed, "free_audits_remaining": user.free_audits_remaining}

@app.post("/billing/checkout")
def billing_checkout(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(status_code=401, detail="Authorization required")
    data = jwt_verify(authorization.split(" ",1)[1])
    with safe_session() as db:
        if not db: raise HTTPException(status_code=503, detail="Database unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        try:
            import stripe as _stripe
            if not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
                user.subscribed = True; db.commit()
                return {"message":"Stripe not configured — subscription activated (demo).", "url": None}
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
            return {"message":"Webhook secret not configured"}
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature", "")
        event = _stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    type_ = event["type"]; data = event["data"]["object"]
    with safe_session() as db:
        if not db: return {"received": True, "db":"unavailable"}
        try:
            if type_ in ("checkout.session.completed","invoice.payment_succeeded"):
                email = data.get("customer_details", {}).get("email") or data.get("customer_email")
                if not email and data.get("customer"):
                    cust = stripe.Customer.retrieve(data["customer"]); email = cust.get("email")
                if email:
                    user = db.query(User).filter(User.email == email.lower()).first()
                    if user:
                        user.subscribed = True
                        if not user.stripe_customer_id and data.get("customer"):
                            user.stripe_customer_id = data["customer"]
                        db.commit()
        except Exception as e: print("[STRIPE WEBHOOK ERROR]", e)
    return {"received": True}

# ---------------------- Admin ----------------------
@app.get("/admin/users")
def admin_users(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(status_code=403, detail="Admin required")
    data = jwt_verify(authorization.split(" ",1)[1])
    with safe_session() as db:
        if not db: raise HTTPException(status_code=503, detail="Database unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        if not user or user.role != "admin": raise HTTPException(status_code=403, detail="Admin required")
        users = db.query(User).order_by(User.created_at.desc()).all()
        return [{"id": u.id, "email": u.email, "verified": u.is_verified, "role": u.role,
                 "timezone": u.timezone, "free_audits_remaining": u.free_audits_remaining,
                 "subscribed": u.subscribed, "created_at": u.created_at.isoformat(),
                 "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None} for u in users]

@app.get("/admin/audits")
def admin_audits(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(status_code=403, detail="Admin required")
    data = jwt_verify(authorization.split(" ",1)[1])
    with safe_session() as db:
        if not db: raise HTTPException(status_code=503, detail="Database unavailable")
        user = db.query(User).filter(User.id == data.get("uid")).first()
        if not user or user.role != "admin": raise HTTPException(status_code=403, detail="Admin required")
        audits = db.query(Audit).order_by(Audit.created_at.desc()).limit(200).all()
        return [{"id": a.id, "url": a.url, "website_id": a.website_id, "overall": a.overall,
                 "grade": a.grade, "errors": a.errors, "warnings": a.warnings, "notices": a.notices,
                 "created_at": a.created_at.isoformat()} for a in audits]

# ---------------------- Scheduler (async; non-blocking) ----------------------
async def scheduler_loop():
    await asyncio.sleep(3)
    while True:
        try:
            with safe_session() as db:
                if not db: await asyncio.sleep(SCHEDULER_INTERVAL); continue
                now_utc = datetime.utcnow().replace(second=0, microsecond=0)
                schedules = db.query(Schedule).filter(Schedule.enabled == True).all()
                for s in schedules:
                    user = db.get(User, s.user_id) if hasattr(db, "get") else db.query(User).get(s.user_id)
                    if not user or not user.subscribed: continue
                    hh, mm = map(int, (s.time_of_day or "09:00").split(":"))
                    try:
                        from zoneinfo import ZoneInfo
                        tz = ZoneInfo(s.timezone or "UTC")
                        local_now = now_utc.replace(tzinfo=timezone.utc).astimezone(tz)
                        scheduled_local = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                        scheduled_utc = scheduled_local.astimezone(timezone.utc).replace(tzinfo=None)
                    except Exception:
                        scheduled_utc = now_utc.replace(hour=hh, minute=mm, second=0, microsecond=0)
                    if now_utc >= scheduled_utc and (not s.last_run_at or s.last_run_at < scheduled_utc):
                        site = db.get(Website, s.website_id) if hasattr(db, "get") else db.query(Website).get(s.website_id)
                        if not site: continue
                        payload = run_actual_audit(site.url)
                        # Email 1-page PDF snapshot
                        from reportlab.lib.pagesizes import A4
                        from reportlab.pdfgen import canvas
                        from reportlab.lib.units import mm
                        buf = io.BytesIO(); cpdf = canvas.Canvas(buf, pagesize=A4)
                        cpdf.setFont("Helvetica-Bold", 14); cpdf.drawString(20*mm, A4[1]-30*mm, f"Audit: {site.url} ({payload['grade']} / {payload['overall']}%)")
                        cpdf.showPage(); cpdf.save(); pdf_bytes = buf.getvalue(); buf.close()
                        subj = f"FF Tech Audit — {site.url} ({payload['grade']} / {payload['overall']}%)"
                        body = "Your scheduled audit is ready.\nCertified PDF attached.\n— FF Tech"
                        send_email(user.email, subj, body, [(f"fftech_audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf", pdf_bytes)])
                        # persist
                        row = Audit(
                            website_id=site.id, url=site.url, overall=payload["overall"], grade=payload["grade"],
                            errors=payload["errors"], warnings=payload["warnings"], notices=payload["notices"],
                            summary=payload["summary"], cat_scores_json=json.dumps(payload["cat_scores"]),
                            metrics_json=json.dumps(payload["metrics"])
                        )
                        db.add(row); s.last_run_at = now_utc; db.commit()
        except Exception as e:
            print("[SCHEDULER ERROR]", e)
        await asyncio.sleep(SCHEDULER_INTERVAL)

# ---------------------- DB INIT (async; non-blocking) ----------------------
def apply_schema_patches_committed():
    with engine.begin() as conn:
        Base.metadata.create_all(bind=engine)

async def init_db():
    max_attempts = int(os.getenv("DB_CONNECT_MAX_ATTEMPTS","10"))
    delay = float(os.getenv("DB_CONNECT_RETRY_DELAY","2"))
    try:
        sanitized = DATABASE_URL
        if "@" in sanitized and "://" in sanitized:
            head, tail = sanitized.split("://", 1)
            userpass_host = tail.split("@")
            if len(userpass_host)==2:
                userpass, hostpart = userpass_host
                user = userpass.split(":")[0]
                sanitized = f"{head}://{user}:***@{hostpart}"
        print("[DB] Using DATABASE_URL:", sanitized)
    except Exception: pass
    for attempt in range(1, max_attempts+1):
        try:
            with engine.begin() as conn: conn.execute(sa_text("SELECT 1"))
            apply_schema_patches_committed()
            print("[DB] Connected & tables ensured"); return
        except OperationalError as e:
            print(f"[DB] Attempt {attempt}/{max_attempts} failed: {e}")
        except Exception as e:
            print(f"[DB] Init error: {e}")
        await asyncio.sleep(delay)
    print("[DB WARNING] DB unavailable after retries; app serves limited functionality")

@app.on_event("startup")
async def on_startup():
    # Healthcheck FIX: do not block startup; these run in background
    asyncio.create_task(init_db())
    if SCHEDULER_INTERVAL > 0:
        asyncio.create_task(scheduler_loop())

# ---------------------- EMAIL ----------------------
def send_email(to_email: str, subject: str, body: str, attachments: list[tuple[str, bytes]] | None = None):
    """
    SMTP send if configured; else print (dev). Attachments: list of (filename, bytes).
    """
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS or not EMAIL_SENDER:
        print(f"[EMAIL FAKE SEND] To: {to_email} | Subject: {subject}\n{body[:600]}\nAttachments: {len(attachments or [])}")
        return
    import ssl, smtplib
    from email.message import EmailMessage
    msg = EmailMessage(); msg["From"] = EMAIL_SENDER; msg["To"] = to_email; msg["Subject"] = subject
    msg.set_content(body)
    for fname, data in (attachments or []):
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=fname)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(SMTP_USER, SMTP_PASS); server.send_message(msg)

# ---------------------- GLOBAL ERROR HANDLER ----------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    try: print("[UNCAUGHT ERROR]", type(exc).__name__, str(exc))
    except Exception: pass
    return JSONResponse(status_code=500, content={"error":"Internal Server Error","message":str(exc)[:500]})

# ---------------------- MAIN ----------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
