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

# --- DATABASE ---
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

# --- AUDIT ENGINE ---
def run_website_audit(url: str):
    if not url.startswith('http'): url = 'https://' + url
    h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}

    try:
        start = time.time()
        res = requests.get(url, headers=h, timeout=20, verify=True)
        soup = BeautifulSoup(res.text, 'html.parser')
        m = {}
        
        # SEO Checks
        m["Title Tag"] = soup.title.string.strip() if soup.title else "Missing"
        m["H1 Count"] = len(soup.find_all('h1'))
        m["H2 Count"] = len(soup.find_all('h2'))
        m["Meta Desc"] = "Yes" if soup.find('meta', attrs={'name': 'description'}) else "No"
        m["Total Images"] = len(soup.find_all('img'))
        m["Links"] = len(soup.find_all('a'))
        m["Viewport"] = "Yes" if soup.find('meta', name='viewport') else "No"
        
        # Technical Checks
        m["SSL"] = "Yes" if url.startswith('https') else "No"
        m["Page Size"] = f"{round(len(res.content)/1024, 2)} KB"
        m["Load Time"] = f"{round(time.time()-start, 2)}s"
        m["Scripts"] = len(soup.find_all('script'))
        m["Forms"] = len(soup.find_all('form'))
        
        # Social
        m["OG Title"] = "Yes" if soup.find('meta', property='og:title') else "No"
        m["Twitter Card"] = "Yes" if soup.find('meta', name='twitter:card') else "No"
        
        # THE FIX FOR LINE 97/100
        has_comments = "
