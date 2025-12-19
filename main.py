import os
import time
import datetime
import requests
from bs4 import BeautifulSoup
from fpdf import FPDF
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, Response, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# --- DATABASE SETUP ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AuditRecord(Base):
    __tablename__ = "audit_reports"
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String)
    grade = Column(String)
    score = Column(Integer)
    metrics = Column(JSON)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Throughweb Audit AI")
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- 45+ METRICS ENGINE ---
def run_website_audit(url: str):
    if not url.startswith('http'): url = 'https://' + url
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

    try:
        start_time = time.time()
        res = requests.get(url, headers=headers, timeout=25, verify=True)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        m = {}
        # SEO & CONTENT (20 METRICS)
        m["Title Tag"] = soup.title.string.strip() if soup.title else "Missing"
        m["Title Length"] = len(m["Title Tag"])
        m["H1 Count"] = len(soup.find_all('h1'))
        m["H2 Count"] = len(soup.find_all('h2'))
        m["H3 Count"] = len(soup.find_all('h3'))
        m["H4 Count"] = len(soup.find_all('h4'))
        m["Meta Description"] = "Present" if soup.find('meta', attrs={'name': 'description'}) else "Missing"
        m["Total Images"] = len(soup.find_all('img'))
        m["Images Missing Alt"] = len([i for i in soup.find_all('img') if not i.get('alt')])
        m["Total Links"] = len(soup.find_all('a'))
        m["External Links"] = len([a for a in soup.find_all('a', href=True) if not a['href'].startswith(url) and not a['href'].startswith('/')])
        m["Canonical Tag"] = "Found" if soup.find('link', rel='canonical') else "Missing"
        m["Word Count"] = len(soup.get_text().split())
        m["Language"] = soup.html.get('lang', 'Not Specified') if soup.html else "Missing"
        m["Viewport Meta"] = "Configured" if soup.find('meta', name='viewport') else "Missing"
        m["Charset Meta"] = "Found" if soup.find('meta', charset=True) else "Missing"
        m["Favicon"] = "Found" if soup.find('link', rel='icon') else "Missing"
        m["Robots Meta"] = "Found" if soup.find('meta', name='robots') else "Missing"
        m["Base URL Set"] = "Yes" if soup.find('base') else "No"
        m["Bold Tags Count"] = len(soup.find_all(['b', 'strong']))

        # TECHNICAL & SECURITY (15 METRICS)
        m["SSL Active"] = "Yes" if url.startswith('https') else "No"
        m["Server Software"] = res.headers.get('Server', 'Hidden')
        m["Full Load Time"] = f"{round(time.time() - start_time, 2)}s"
        m["Page Size"] = f"{round(len(res.content) / 1024, 2)} KB"
        m["HSTS Header"] = "Enabled" if 'Strict-Transport-Security' in res.headers else "Disabled"
        m["X-Frame-Options"] = res.headers.get('X-Frame-Options', 'Not Set')
        m["X-Content-Type"] = res.headers.get('X-Content-Type-Options', 'Not Set')
        m["Compression"] = res.headers.get('Content-Encoding', 'None')
        m["Scripts Count"] = len(soup.find_all('script'))
        m["External CSS"] = len(soup.find_all('link', rel='stylesheet'))
        m["Inline Styles"] = len(soup.find_all('style'))
        m["Forms Found"] = len(soup.find_all('form'))
        m["iFrames Found"] = len(soup.find_all('iframe'))
        m["Tables Found"] = len(soup.find_all('table'))
        m["Video Elements"] = len(soup.find_all('video'))

        # SOCIAL & STRUCTURE (10 METRICS)
        m["OG Title"] = "Present" if soup.find('meta', property='og:title') else "Missing"
        m["OG Description"] = "Present" if soup.find('meta', property='og:description') else "Missing"
        m["OG Image"] = "Present" if soup.find('meta', property='og:image') else "Missing"
        m["Twitter Card"] = "Present" if soup.find('meta', name='twitter:card') else "Missing"
        m["Schema JSON-LD"] = "Found" if soup.find('script', type='application/ld+json') else "Missing"
        m["Copyright Info"] = "Found" if "©" in soup.get_text() else "Not Found"
        m["Social Links"] = len([a for a in soup.find_all('a', href=True) if any(x in a['href'] for x in ['facebook', 'twitter', 'linkedin'])])
        m["Comments in Code"] = "Yes" if soup.find(string=lambda text: isinstance(text, str) and "
