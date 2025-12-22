# fastapi_web_audit.py
import io, requests, urllib3, re
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
from fpdf import FPDF

# Silence SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(title="FF TECH ELITE")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'FFTechElite/3.0'})

# ====================== Utilities ======================
def ensure_http_scheme(u: str) -> str:
    u = u.strip()
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "https://" + u
    return u

def safe_get(url: str, timeout=12) -> Optional[requests.Response]:
    try:
        return SESSION.get(url, timeout=timeout, verify=False, allow_redirects=True)
    except Exception:
        return None

def text_len(s: Optional[str]) -> int:
    return len(s.strip()) if s else 0

def clamp(v: float, min_v: float = 0.0, max_v: float = 100.0) -> float:
    return max(min_v, min(max_v, v))

def ratio(part: int, whole: int) -> float:
    return (part / whole) if whole > 0 else 0.0

# ====================== Metric Functions ======================
def https_enabled(url: str) -> float:
    return 100.0 if url.startswith("https://") else 0.0

def title_tag_present(soup: BeautifulSoup) -> float:
    return 100.0 if soup.title and text_len(soup.title.string or "") > 0 else 0.0

def meta_description_present(soup: BeautifulSoup) -> float:
    return 100.0 if soup.find("meta", {"name": "description"}) else 0.0

def canonical_tag_present(soup: BeautifulSoup) -> float:
    return 100.0 if soup.find("link", {"rel": "canonical"}) else 50.0

def robots_txt_accessible(base_url: str) -> float:
    url = urljoin(base_url, "/robots.txt")
    resp = safe_get(url)
    return 100.0 if resp and resp.status_code < 400 else 60.0

def page_size_score(resp: requests.Response) -> float:
    size_bytes = len(resp.content or b'')
    if size_bytes <= 1_000_000: return 100.0
    if size_bytes >= 3_000_000: return 0.0
    return 100.0 * (3_000_000 - size_bytes) / 2_000_000

# Add more metric functions as needed following similar patterns...

# ====================== Audit Function ======================
def audit_website(url: str) -> Dict[str, float]:
    url = ensure_http_scheme(url)
    resp = safe_get(url)
    if not resp:
        return {"Error": "Site not reachable"}
    soup = BeautifulSoup(resp.text, "html.parser")

    scores = {
        "HTTPS Enabled": https_enabled(url),
        "Title Tag Present": title_tag_present(soup),
        "Meta Description Present": meta_description_present(soup),
        "Canonical Tag Present": canonical_tag_present(soup),
        "Robots.txt Accessible": robots_txt_accessible(url),
        "Page Size Optimized": page_size_score(resp),
    }

    # More metrics can be added here...

    return scores

# ====================== Routes ======================
@app.get("/", response_class=HTMLResponse)
def home():
    with open("audit_frontend.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/audit")
def audit_site(url: str):
    scores = audit_website(url)
    return scores

@app.get("/audit/pdf")
def audit_pdf(url: str):
    scores = audit_website(url)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"Website Audit Report: {url}", ln=True)
    pdf.set_font("Arial", '', 12)
    for k, v in scores.items():
        pdf.cell(0, 10, f"{k}: {v}%", ln=True)
    pdf_output = io.BytesIO()
    pdf.output(pdf_output)
    pdf_output.seek(0)
    return StreamingResponse(pdf_output, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=audit_report.pdf"})
