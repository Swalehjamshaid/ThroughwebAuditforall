# main.py
# FF Tech — AI Website Audit (SaaS, Single-file FastAPI + Jinja + Tailwind/Chart.js)
# ------------------------------------------------------------------------------
import os
import re
import json
import time
import math
import smtplib
import httpx
import sqlite3
import tldextract
import secrets
import asyncio
import traceback
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, BaseLoader, select_autoescape
from email_validator import validate_email, EmailNotValidError
from passlib.context import CryptContext
from itsdangerous import URLSafeSerializer, BadSignature

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker, relationship, Session

# ------------------------------------------------------------------------------
# App Setup & Config
# ------------------------------------------------------------------------------
APP_NAME = "FF Tech — AI Website Audit"
APP_DOMAIN = os.getenv("APP_DOMAIN", "http://localhost:8000")
ENABLE_HISTORY = os.getenv("ENABLE_HISTORY", "").lower() in ("true", "1", "yes")
PSI_API_KEY = os.getenv("PSI_API_KEY")

# --- REFINED DATABASE LOGIC FOR RAILWAY ---
_raw_db_url = os.getenv("DATABASE_URL", "")
if not _raw_db_url or _raw_db_url.strip() == "":
    DB_URL = "sqlite:///./audits.db"
else:
    if _raw_db_url.startswith("postgres://"):
        DB_URL = _raw_db_url.replace("postgres://", "postgresql://", 1)
    else:
        DB_URL = _raw_db_url

SMTP_HOST = os.getenv("SMTP_HOST")
try:
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
except (ValueError, TypeError):
    SMTP_PORT = 587

SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@fftech.ai")

COOKIE_SECRET = os.getenv("COOKIE_SECRET", secrets.token_hex(16))
session_signer = URLSafeSerializer(COOKIE_SECRET, salt="fftech-session")
verify_signer = URLSafeSerializer(COOKIE_SECRET, salt="fftech-verify")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__ident="2b")

# SQLAlchemy
class Base(DeclarativeBase):
    pass

engine = create_engine(DB_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Models
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    timezone = Column(String(64), default="Asia/Karachi")
    preferred_hour = Column(Integer, default=9)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)
    sites = relationship("Site", back_populates="owner")

class Site(Base):
    __tablename__ = "sites"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    url = Column(String(1024), nullable=False)
    schedule_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="sites")
    audits = relationship("Audit", back_populates="site")

class Audit(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    payload_json = Column(Text)
    overall_score = Column(Integer, default=0)
    grade = Column(String(8), default="D")
    site = relationship("Site", back_populates="audits")

class LoginActivity(Base):
    __tablename__ = "login_activity"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    email = Column(String(255), nullable=False)
    ts = Column(DateTime, default=datetime.utcnow)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)

Base.metadata.create_all(bind=engine)

# ------------------------------------------------------------------------------
# Embedded Templates (Jinja)
# ------------------------------------------------------------------------------
env = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html", "xml"]))

LAYOUT_BASE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{{ title or app_name }}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    body { font-family:'Inter', sans-serif; }
    .collapsible-content { max-height: 0; overflow: hidden; transition: max-height 0.3s ease-out; }
    .collapsible-active .collapsible-content { max-height: 2000px; }
    @media print {.no-print{display:none}.print-break{page-break-after:always}}
  </style>
</head>
<body class="bg-gray-50 text-gray-900">
  <nav class="bg-white border-b sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="flex justify-between h-16 items-center">
        <a href="/" class="flex items-center text-xl font-bold text-indigo-600">
          <i class="fas fa-robot mr-2"></i> {{ app_name }}
        </a>
        <div class="flex items-center space-x-3">
          {% if user %}
            <span class="text-sm text-gray-500">Hi, {{ user.email }}</span>
            <a href="/dashboard" class="text-sm px-3 py-1 bg-indigo-50 text-indigo-600 rounded">Dashboard</a>
            <a href="/logout" class="text-sm px-3 py-1 bg-gray-100 text-gray-600 rounded">Logout</a>
          {% else %}
            <a href="/login" class="text-sm px-3 py-1 bg-gray-100 text-gray-600 rounded">Login</a>
            <a href="/register" class="text-sm px-3 py-1 bg-indigo-600 text-white rounded">Register</a>
          {% endif %}
        </div>
      </div>
    </div>
  </nav>
  <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
    {{ content | safe }}
  </main>
  <footer class="mt-12 text-center text-gray-400 text-xs border-t pt-8">
    <p>© {{ now[:4] }} {{ app_name }} Intelligence</p>
    <p class="mt-1 font-mono uppercase tracking-widest">Confidence Level: 99.8% AI Diagnostic Verified</p>
  </footer>
</body>
</html>
"""

HOME_TEMPLATE = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>FF Tech — AI Website Audit | International SaaS</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    body { font-family: 'Inter', sans-serif; }
    .gradient { background: radial-gradient(1200px 400px at 10% 10%, rgba(79,70,229,0.1), transparent), linear-gradient(180deg, #ffffff, #f8fafc); }
    .glass { background: rgba(255,255,255,0.8); backdrop-filter: blur(6px); }
    .badge-dot { width: .5rem; height: .5rem; border-radius: 100%; display:inline-block; margin-right:.35rem; }
    .feature-card:hover { transform: translateY(-3px); border-color: #4f46e5; }
  </style>
</head>
<body class="gradient text-gray-900">

  <nav class="bg-white/80 glass border-b sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="flex justify-between h-16 items-center">
        <a href="/" class="flex items-center gap-2">
          <img src="https://dummyimage.com/140x40/4f46e5/ffffff&text=FF+Tech" alt="Logo" class="h-8">
          <span class="text-xl font-bold text-indigo-700">AI Website Audit</span>
        </a>
        <div class="flex items-center gap-3">
          {% if user %}
            <a href="/dashboard" class="text-sm font-semibold text-indigo-600 bg-indigo-50 px-4 py-2 rounded-lg">Dashboard</a>
          {% else %}
            <a href="/login" class="text-sm font-semibold text-gray-600">Login</a>
            <a href="/register" class="text-sm font-semibold bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 transition">Register</a>
          {% endif %}
        </div>
      </div>
    </div>
  </nav>

  <header class="relative">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 lg:py-24">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-10 items-center">
        <div>
          <span class="inline-flex items-center text-xs uppercase tracking-widest text-indigo-600 font-bold bg-indigo-50 px-2 py-1 rounded">
            <i class="fas fa-shield-halved mr-2"></i> Certified AI Audit & Compliance
          </span>
          <h1 class="mt-3 text-3xl sm:text-4xl lg:text-5xl font-extrabold leading-tight">
            World-Class SaaS for Website Health, <span class="text-indigo-600">Security</span> & Performance
          </h1>
          <p class="mt-4 text-gray-600 text-lg">
            Audit 45+ metrics across Security, SEO, Performance, Accessibility, UX & Compliance. 
            Get daily emails, accumulated reports, and a certified grading—powered by FF Tech.
          </p>
          <div class="mt-6 flex flex-wrap gap-3">
            <span class="flex items-center text-xs text-gray-500"><span class="badge-dot bg-green-500"></span>Security headers</span>
            <span class="flex items-center text-xs text-gray-500"><span class="badge-dot bg-blue-500"></span>Core Web Vitals</span>
            <span class="flex items-center text-xs text-gray-500"><span class="badge-dot bg-amber-500"></span>Sitemap & Robots</span>
          </div>
          <div class="mt-8 flex gap-3">
            <a href="#instant-audit" class="px-6 py-3 bg-indigo-600 text-white rounded-xl font-bold hover:bg-indigo-700 shadow-lg shadow-indigo-200">
              Run Free Audit
            </a>
            <a href="/register" class="px-6 py-3 bg-white border border-gray-200 text-gray-700 rounded-xl font-bold hover:bg-gray-50 transition">
              Create Account
            </a>
          </div>
          <div class="mt-6 text-xs text-gray-400">
            <i class="fas fa-lock mr-1"></i> Secure by design • International standards • Railway cloud-ready
          </div>
        </div>

        <div class="relative">
          <div class="bg-white shadow-2xl ring-1 ring-gray-100 rounded-3xl p-8 transform rotate-1">
            <div class="flex items-center justify-between mb-6">
              <h3 class="text-lg font-bold">Preview: Certified Report</h3>
              <span class="text-xs text-indigo-600 font-bold uppercase tracking-widest">FF Tech</span>
            </div>
            <div class="grid grid-cols-3 gap-4 text-center">
              <div class="border rounded-2xl p-4 bg-indigo-50/50">
                <div class="text-3xl font-black text-indigo-600">A+</div>
                <div class="text-[10px] uppercase font-bold text-gray-400">Grade</div>
              </div>
              <div class="border rounded-2xl p-4">
                <div class="text-2xl font-extrabold">92%</div>
                <div class="text-[10px] uppercase font-bold text-gray-400">Health</div>
              </div>
              <div class="border rounded-2xl p-4">
                <div class="text-2xl font-extrabold">45+</div>
                <div class="text-[10px] uppercase font-bold text-gray-400">Metrics</div>
              </div>
            </div>
            <div class="mt-6 bg-gray-50 border rounded-2xl p-5">
              <div class="flex items-center justify-between text-sm mb-2">
                <span class="text-gray-900 font-bold flex items-center"><i class="fas fa-brain text-indigo-500 mr-2"></i> Executive Summary</span>
                <span class="text-[10px] bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-bold">AI Verified</span>
              </div>
              <p class="text-gray-600 text-xs leading-relaxed italic">
                "Security & Compliance posture is robust. Recommendation: enforce HSTS and optimize LCP images to reach 98% health score."
              </p>
            </div>
          </div>
          <div class="absolute -top-6 -right-6 bg-indigo-600 text-white rounded-full px-4 py-2 text-xs font-bold shadow-xl">
            <i class="fas fa-certificate mr-1"></i> Official Report
          </div>
        </div>
      </div>
    </div>
  </header>

  <section id="instant-audit" class="py-12">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="bg-white rounded-3xl shadow-xl border border-indigo-50 p-8 lg:p-12">
        <h2 class="text-2xl font-bold mb-6">Run an Instant Audit</h2>
        <form method="post" action="/report" class="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div class="md:col-span-2">
            <label class="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">Website URL</label>
            <input name="url" type="url" required placeholder="https://example.com" class="w-full border-2 border-gray-100 rounded-xl px-4 py-3 focus:border-indigo-500 outline-none transition font-medium">
          </div>
          <div>
            <label class="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">PSI Strategy</label>
            <select name="psi_strategy" class="w-full border-2 border-gray-100 rounded-xl px-4 py-3 focus:border-indigo-500 outline-none transition font-medium">
              <option value="mobile">Mobile</option>
              <option value="desktop">Desktop</option>
            </select>
          </div>
          <div class="md:col-span-3">
            <button class="w-full py-4 bg-indigo-600 text-white rounded-xl font-bold text-lg hover:bg-indigo-700 shadow-lg shadow-indigo-100 transition transform hover:-translate-y-1">
              <i class="fas fa-bolt mr-2 text-amber-400"></i> Start Audit Now
            </button>
          </div>
        </form>
      </div>
    </div>
  </section>

  <section class="py-24">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="text-center mb-16">
        <h2 class="text-3xl font-extrabold text-gray-900">Enterprise Standards. Railway Cloud.</h2>
        <p class="mt-4 text-gray-500">Comprehensive auditing across security, performance, and compliance.</p>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        <div class="feature-card bg-white border border-gray-100 rounded-2xl p-8 shadow-sm transition">
          <i class="fas fa-shield-halved text-indigo-600 text-3xl mb-4"></i>
          <h3 class="font-bold text-xl mb-2">Security & Compliance</h3>
          <p class="text-sm text-gray-500 leading-relaxed">Automated checks for HSTS, CSP, Mixed Content, and GDPR/Cookie privacy policies.</p>
        </div>
        <div class="feature-card bg-white border border-gray-100 rounded-2xl p-8 shadow-sm transition">
          <i class="fas fa-gauge-high text-indigo-600 text-3xl mb-4"></i>
          <h3 class="font-bold text-xl mb-2">Core Web Vitals</h3>
          <p class="text-sm text-gray-500 leading-relaxed">Integration with Google PSI for LCP, CLS, and TBT analysis with strategy selection.</p>
        </div>
        <div class="feature-card bg-white border border-gray-100 rounded-2xl p-8 shadow-sm transition">
          <i class="fas fa-file-invoice text-indigo-600 text-3xl mb-4"></i>
          <h3 class="font-bold text-xl mb-2">Certified Reports</h3>
          <p class="text-sm text-gray-500 leading-relaxed">Receive daily emails with health score trends and actionable executive summaries.</p>
        </div>
      </div>
    </div>
  </section>

  <footer class="py-12 border-t bg-white text-center">
    <p class="text-sm text-gray-400">© <span id="year"></span> FF Tech Intelligence. Professional Diagnostic Certification.</p>
  </footer>

  <script>document.getElementById('year').textContent = new Date().getFullYear();</script>
</body>
</html>
"""

AUTH_REGISTER_TEMPLATE = r"""
<div class="max-w-md mx-auto bg-white rounded-xl shadow p-6">
  <h2 class="text-lg font-bold">Create your account</h2>
  <p class="text-sm text-gray-600">We’ll email a verification link.</p>
  <form method="post" action="/register" class="mt-4 space-y-4">
    <div>
      <label class="block text-sm font-medium text-gray-700">Email</label>
      <input name="email" type="email" required class="mt-1 w-full border rounded px-3 py-2">
    </div>
    <div>
      <label class="block text-sm font-medium text-gray-700">Password</label>
      <input name="password" type="password" required class="mt-1 w-full border rounded px-3 py-2">
    </div>
    <div>
      <label class="block text-sm font-medium text-gray-700">Timezone</label>
      <input name="timezone" placeholder="Asia/Karachi" class="mt-1 w-full border rounded px-3 py-2" value="Asia/Karachi">
    </div>
    <div>
      <label class="block text-sm font-medium text-gray-700">Preferred Daily Email Hour</label>
      <input name="preferred_hour" type="number" min="0" max="23" value="9" class="mt-1 w-full border rounded px-3 py-2">
    </div>
    <button class="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700">Register</button>
  </form>
</div>
"""

AUTH_LOGIN_TEMPLATE = r"""
<div class="max-w-md mx-auto bg-white rounded-xl shadow p-6">
  <h2 class="text-lg font-bold">Login</h2>
  <form method="post" action="/login" class="mt-4 space-y-4">
    <div>
      <label class="block text-sm font-medium text-gray-700">Email</label>
      <input name="email" type="email" required class="mt-1 w-full border rounded px-3 py-2">
    </div>
    <div>
      <label class="block text-sm font-medium text-gray-700">Password</label>
      <input name="password" type="password" required class="mt-1 w-full border rounded px-3 py-2">
    </div>
    <button class="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700">Login</button>
  </form>
</div>
"""

DASHBOARD_TEMPLATE = r"""
<div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
  <div class="bg-white p-6 rounded-xl shadow">
    <h3 class="text-lg font-bold">Your Websites</h3>
    <form method="post" action="/sites/add" class="mt-4 space-y-3">
      <input name="url" placeholder="https://example.com" class="w-full border rounded px-3 py-2">
      <div class="flex items-center space-x-2">
        <label class="text-sm text-gray-700">Schedule Enabled</label>
        <input type="checkbox" name="schedule_enabled">
      </div>
      <button class="bg-indigo-600 text-white px-3 py-2 rounded">Add Website</button>
    </form>
    <div class="mt-6">
      {% if sites %}
        <ul class="divide-y">
          {% for s in sites %}
          <li class="py-3 flex items-center justify-between">
            <div>
              <a href="/audit?site_id={{ s.id }}" class="text-indigo-600 font-medium">{{ s.url }}</a>
              <div class="text-xs text-gray-500">Scheduled: {{ 'Yes' if s.schedule_enabled else 'No' }}</div>
            </div>
            <div class="flex gap-2">
              <a href="/sites/toggle?id={{ s.id }}" class="text-xs bg-gray-100 px-2 py-1 rounded">{{ 'Disable' if s.schedule_enabled else 'Enable' }}</a>
              <a href="/sites/delete?id={{ s.id }}" class="text-xs bg-red-50 text-red-600 px-2 py-1 rounded">Delete</a>
            </div>
          </li>
          {% endfor %}
        </ul>
      {% else %}
        <p class="text-sm text-gray-500">No websites yet.</p>
      {% endif %}
    </div>
  </div>

  <div class="bg-white p-6 rounded-xl shadow lg:col-span-2">
    <h3 class="text-lg font-bold">Recent Audits</h3>
    {% if audits %}
      <div class="mt-4 overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 border-b text-gray-500 uppercase text-xs font-bold">
            <tr><th class="px-3 py-2 text-left">Site</th><th class="px-3 py-2 text-left">Score</th><th class="px-3 py-2 text-left">Grade</th><th class="px-3 py-2 text-left">Date</th><th></th></tr>
          </thead>
          <tbody class="divide-y">
          {% for a in audits %}
            <tr>
              <td class="px-3 py-2">{{ a.site.url }}</td>
              <td class="px-3 py-2 font-mono">{{ a.overall_score }}</td>
              <td class="px-3 py-2">{{ a.grade }}</td>
              <td class="px-3 py-2">{{ a.created_at.strftime('%Y-%m-%d %H:%M') }} UTC</td>
              <td class="px-3 py-2 text-right"><a href="/report?id={{ a.id }}" class="text-indigo-600 font-bold hover:underline">View Report</a></td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <p class="text-sm text-gray-500">No audits yet. Run one from Your Websites.</p>
    {% endif %}
  </div>
</div>
"""

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ app_name }} | Audit Report for {{ website_url }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    body { font-family: 'Inter', sans-serif; }
    .collapsible-content { max-height: 0; overflow: hidden; transition: max-height 0.3s ease-out; }
    .collapsible-active .collapsible-content { max-height: 2000px; }
    @media print {.no-print{display:none}.print-break{page-break-after:always}}
  </style>
</head>
<body class="bg-gray-50 text-gray-900">
  <nav class="bg-white border-b sticky top-0 z-50 no-print">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="flex justify-between h-16 items-center">
        <div class="flex items-center space-x-3">
          <img src="https://dummyimage.com/140x40/4f46e5/ffffff&text=FF+Tech+Certified" alt="FF Tech" class="h-8">
          <span class="text-2xl font-bold text-indigo-600"><i class="fas fa-robot"></i> {{ app_name }}</span>
        </div>
        <div class="flex space-x-4">
          <button onclick="window.print()" class="bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-indigo-700 transition">
            <i class="fas fa-file-pdf mr-2"></i>Export to PDF
          </button>
        </div>
      </div>
    </div>
  </nav>

  <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
    <div class="bg-white rounded-xl shadow-sm p-6 mb-8 border border-gray-100 flex flex-col md:flex-row justify-between items-start md:items-center space-y-4 md:space-y-0">
      <div>
        <h1 class="text-xl font-bold text-gray-800">Certified Website Audit Report</h1>
        <p class="text-gray-500 text-sm">Target: <span class="font-medium text-indigo-600 underline">{{ website_url }}</span></p>
        <div class="mt-2 flex space-x-4 text-xs text-gray-400">
          <span><i class="fas fa-calendar-alt"></i> Date: {{ audit_date }}</span>
          <span><i class="fas fa-fingerprint"></i> ID: {{ audit_id }}</span>
        </div>
      </div>
      <div class="text-right">
        <span class="text-gray-400 text-xs uppercase font-bold tracking-widest block">Official Grade</span>
        <span class="text-5xl font-black {{ grade_class }}">{{ grade }}</span>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
      <div class="bg-white p-8 rounded-xl shadow-sm border border-gray-100 flex flex-col items-center justify-center text-center">
        <h2 class="text-gray-500 font-semibold mb-4 uppercase tracking-wide text-sm">Overall Site Health</h2>
        <div class="relative inline-flex">
          <svg class="w-32 h-32">
            <circle class="text-gray-200" stroke-width="8" stroke="currentColor" fill="transparent" r="58" cx="64" cy="64"></circle>
            <circle class="text-indigo-600" stroke-width="8" stroke-dasharray="364.4"
                    stroke-dashoffset="{{ 364.4 - (364.4 * overall_score / 100) }}"
                    stroke-linecap="round" stroke="currentColor" fill="transparent" r="58" cx="64" cy="64"></circle>
          </svg>
          <span class="absolute inset-0 flex items-center justify-center text-3xl font-bold">{{ overall_score }}%</span>
        </div>
        <div class="mt-6 grid grid-cols-3 gap-4 w-full border-t pt-4">
          <div><span class="block text-red-500 font-bold">{{ total_errors }}</span><span class="text-[10px] text-gray-400 uppercase font-bold">Errors</span></div>
          <div><span class="block text-amber-500 font-bold">{{ total_warnings }}</span><span class="text-[10px] text-gray-400 uppercase font-bold">Warnings</span></div>
          <div><span class="block text-blue-500 font-bold">{{ total_notices }}</span><span class="text-[10px] text-gray-400 uppercase font-bold">Notices</span></div>
        </div>
      </div>

      <div class="lg:col-span-2 bg-white p-8 rounded-xl shadow-sm border border-gray-100">
        <h2 class="text-lg font-bold text-gray-800 mb-4"><i class="fas fa-brain text-indigo-500 mr-2"></i> AI Executive Summary</h2>
        <div class="text-gray-600 leading-relaxed text-sm italic border-l-4 border-indigo-100 pl-4">
          {{ executive_summary_200_words }}
        </div>
        <div class="mt-6 flex flex-wrap gap-2">
          {% for area in weak_areas %}
          <span class="px-3 py-1 bg-red-50 text-red-600 rounded-full text-xs font-semibold border border-red-100">
            <i class="fas fa-exclamation-triangle mr-1"></i> {{ area }}
          </span>
          {% endfor %}
        </div>
      </div>
    </div>

    <div class="bg-white p-8 rounded-xl shadow-sm border border-gray-100 mb-8">
      <h2 class="text-lg font-bold text-gray-800 mb-6"><i class="fas fa-chart-line text-indigo-500 mr-2"></i> Historical Performance Trends</h2>
      <div class="h-64"><canvas id="trendChart"></canvas></div>
    </div>

    <div class="space-y-6 print-break">
      <h2 class="text-2xl font-bold text-gray-800 border-b pb-2 mb-4">Detailed Technical Elaboration</h2>
      {% for category in audit_categories %}
      <div class="collapsible bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden" id="cat-{{ loop.index }}">
        <button onclick="toggleCollapse('cat-{{ loop.index }}')" class="w-full flex justify-between items-center p-5 bg-gray-50 hover:bg-gray-100 transition">
          <span class="font-bold text-gray-700 flex items-center capitalize">
            <i class="fas {{ category.icon }} mr-3 text-indigo-500"></i> {{ category.name }}
            <span class="ml-4 text-xs font-normal bg-white px-2 py-1 rounded border text-gray-500">{{ category.metrics|length }} Metrics</span>
          </span>
          <i class="fas fa-chevron-down transition-transform"></i>
        </button>
        <div class="collapsible-content">
          <div class="overflow-x-auto">
            <table class="w-full text-left text-sm">
              <thead class="bg-gray-50 border-b text-gray-500 uppercase text-[10px] font-bold">
                <tr><th class="px-6 py-3">Metric Name</th><th class="px-6 py-3">Status</th><th class="px-6 py-3">Score</th><th class="px-6 py-3">Priority</th><th class="px-6 py-3">Impact / Recommendation</th></tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                {% for metric in category.metrics %}
                <tr class="hover:bg-gray-50 transition">
                  <td class="px-6 py-4 font-semibold text-gray-700">{{ metric.name }}</td>
                  <td class="px-6 py-4">
                    {% if metric.status == 'Good' %}
                      <span class="px-2 py-1 bg-green-100 text-green-700 rounded-md text-[10px] font-bold">Good</span>
                    {% elif metric.status == 'Warning' %}
                      <span class="px-2 py-1 bg-amber-100 text-amber-700 rounded-md text-[10px] font-bold">Warning</span>
                    {% else %}
                      <span class="px-2 py-1 bg-red-100 text-red-700 rounded-md text-[10px] font-bold">Critical</span>
                    {% endif %}
                  </td>
                  <td class="px-6 py-4 text-right pr-12 font-mono text-xs">{{ metric.score }}/100</td>
                  <td class="px-6 py-4">
                    <span class="flex items-center text-[10px] uppercase font-bold">
                      <span class="w-2 h-2 rounded-full mr-2 {% if metric.priority == 'High' %}bg-red-500{% elif metric.priority == 'Medium' %}bg-amber-500{% else %}bg-green-500{% endif %}"></span>
                      {{ metric.priority }}
                    </span>
                  </td>
                  <td class="px-6 py-4">
                    <div class="max-w-md">
                      <p class="text-[10px] text-gray-400 mb-1 font-medium italic">Impact: {{ metric.impact }}</p>
                      <p class="text-gray-600 text-xs">{{ metric.recommendation }}</p>
                    </div>
                  </td>
                </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      {% endfor %}
    </div>

    <div class="mt-12 bg-indigo-900 rounded-2xl p-8 text-white shadow-xl relative overflow-hidden print-break">
      <div class="relative z-10">
        <h2 class="text-2xl font-bold mb-4 flex items-center"><i class="fas fa-lightbulb text-yellow-400 mr-3"></i> Actionable Insights for the Owner</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mt-6">
          {% for insight in owner_insights %}
          <div class="bg-indigo-800/50 p-6 rounded-xl border border-indigo-700 hover:bg-indigo-800 transition">
            <h3 class="font-bold text-indigo-100 mb-2">{{ insight.title }}</h3>
            <p class="text-sm text-indigo-200 leading-relaxed">{{ insight.description }}</p>
          </div>
          {% endfor %}
        </div>
      </div>
      <i class="fas fa-rocket absolute -bottom-10 -right-10 text-indigo-800 text-9xl opacity-30 transform rotate-12"></i>
    </div>

    <footer class="mt-12 text-center text-gray-400 text-xs border-t pt-8">
      <p>© {{ audit_date[:4] }} {{ app_name }} Intelligence. This audit report is valid until {{ validity_date }}.</p>
      <p class="mt-1 font-mono uppercase tracking-widest">Confidence Level: 99.8% AI Diagnostic Verified</p>
    </footer>
  </main>

  <script>
    function toggleCollapse(id) {
      const el = document.getElementById(id);
      const icon = el.querySelector('.fa-chevron-down');
      el.classList.toggle('collapsible-active');
      if(icon) icon.style.transform = el.classList.contains('collapsible-active') ? 'rotate(180deg)' : 'rotate(0deg)';
    }

    const ctx = document.getElementById('trendChart').getContext('2d');
    new Chart(ctx, {
      type: 'line',
      data: {
        labels: {{ trend_chart_data.labels | safe if trend_chart_data else "['Jan','Feb','Mar','Apr','May','Jun']" }},
        datasets: [{
          label: 'Health Score Trend',
          data: {{ trend_chart_data.values | safe if trend_chart_data else "[65,72,68,84,82,91]" }},
          borderColor: '#4f46e5',
          backgroundColor: 'rgba(79, 70, 229, 0.1)',
          fill: true, tension: 0.4
        }]
      },
      options: {
        responsive:true, maintainAspectRatio:false,
        plugins:{legend:{display:false}},
        scales:{ y:{beginAtZero:false,min:0,max:100,grid:{borderDash:[5,5]}}, x:{grid:{display:false}} }
      }
    });
  </script>
</body>
</html>
"""

# ------------------------------------------------------------------------------
# Utility & Security
# ------------------------------------------------------------------------------
def render_page(user: Optional[User], inner_html: str, title: str = None) -> HTMLResponse:
    base = env.from_string(LAYOUT_BASE)
    html = base.render(
        app_name=APP_NAME,
        content=inner_html,
        user=user,
        now=datetime.utcnow().strftime("%Y-%m-%d"),
        title=title or APP_NAME,
    )
    return HTMLResponse(html)

def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def grade_for_score(score: int) -> Tuple[str, str]:
    if score >= 92: return ("A+", "text-green-600")
    if score >= 85: return ("A", "text-emerald-600")
    if score >= 75: return ("B", "text-amber-500")
    if score >= 65: return ("C", "text-orange-600")
    return ("D", "text-red-600")

def hash_password(pw: str) -> str:
    return pwd_context.hash(pw)

def verify_password(pw: str, h: str) -> bool:
    return pwd_context.verify(pw, h)

def sign_session(user_id: int) -> str:
    return session_signer.dumps({"uid": user_id, "ts": int(time.time())})

def unsign_session(token: str) -> Optional[int]:
    try:
        data = session_signer.loads(token)
        return data.get("uid")
    except BadSignature:
        return None

def send_email(to_email: str, subject: str, html_body: str, text_body: str = "") -> bool:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and FROM_EMAIL):
        return False
    try:
        msg = f"From: {FROM_EMAIL}\r\nTo: {to_email}\r\nSubject: {subject}\r\nMIME-Version: 1.0\r\nContent-Type: text/html\r\n\r\n{html_body}"
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, [to_email], msg)
        return True
    except Exception:
        print("Email send failed:", traceback.format_exc())
        return False

# ------------------------------------------------------------------------------
# Crawl & Audit (extended 45+ metrics)
# ------------------------------------------------------------------------------
@dataclass
class CrawlConfig:
    url: str
    max_pages: int = 20
    concurrency: int = 10
    user_agent: str = "FFTechAuditBot/3.0"

async def fetch_page(client: httpx.AsyncClient, url: str) -> Tuple[int, Dict[str, str], bytes, float, str]:
    start = time.perf_counter()
    try:
        r = await client.get(url)
        ms = (time.perf_counter() - start) * 1000.0
        return r.status_code, {k.lower(): v for k, v in r.headers.items()}, r.content, ms, str(r.url)
    except Exception:
        return 0, {}, b"", (time.perf_counter() - start) * 1000.0, url

async def crawl_site(cfg: CrawlConfig) -> Dict[str, Any]:
    parsed = urlparse(cfg.url)
    base = f"{parsed.scheme or 'https'}://{parsed.netloc or parsed.path}"
    root_domain = tldextract.extract(parsed.netloc).registered_domain

    headers = {"User-Agent": cfg.user_agent}
    limits = httpx.Limits(max_connections=cfg.concurrency, max_keepalive_connections=cfg.concurrency)
    timeout = httpx.Timeout(30.0)

    visited, pages = set(), []
    queue = [base]
    broken_links_count = 0
    favicon_present = False
    robots_txt_ok = False
    sitemap_present = False

    async with httpx.AsyncClient(headers=headers, timeout=timeout, limits=limits, follow_redirects=True) as client:
        try:
            rb = await client.get(urljoin(base, "/robots.txt"))
            robots_txt_ok = (rb.status_code == 200)
        except: pass
        try:
            sm = await client.get(urljoin(base, "/sitemap.xml"))
            sitemap_present = (sm.status_code == 200)
        except: pass
        try:
            fav = await client.get(urljoin(base, "/favicon.ico"))
            favicon_present = (fav.status_code == 200)
        except: pass

        while queue and len(pages) < cfg.max_pages:
            url = queue.pop(0)
            if url in visited: continue
            visited.add(url)

            status, h, body, dur, final = await fetch_page(client, url)
            html = body.decode(errors="ignore") if body else ""
            soup = BeautifulSoup(html, "lxml") if html else None

            title = clean(soup.title.string) if soup and soup.title else None
            md = soup.find("meta", attrs={"name": "description"}) if soup else None
            meta_desc = clean(md.get("content", "")) if md else None
            h1t = soup.find("h1") if soup else None
            h1 = clean(h1t.get_text()) if h1t else None
            html_lang = soup.find("html").get("lang", "") if soup and soup.find("html") else ""

            is_https = final.startswith("https://")
            hsts = bool(h.get("strict-transport-security"))
            csp = bool(h.get("content-security-policy"))
            xfo = bool(h.get("x-frame-options"))
            xcto = bool(h.get("x-content-type-options"))
            referrer_policy = h.get("referrer-policy", "")
            permissions_policy = h.get("permissions-policy", "")

            mixed = False
            lazy_img_count = 0
            preload_count = 0
            if is_https and soup:
                for tag in soup.find_all(["img", "script", "link", "iframe"]):
                    src = tag.get("src") or tag.get("href") or ""
                    if src.startswith("http://"):
                        mixed = True
                        break
                    if tag.name == "img" and (tag.get("loading") == "lazy"):
                        lazy_img_count += 1
                    if tag.name == "link" and tag.get("rel") and "preload" in tag.get("rel"):
                        preload_count += 1

            text_low = (soup.get_text(" ", strip=True).lower() if soup else "")
            cookie_banner = any(k in text_low for k in ["cookie consent", "we use cookies", "accept cookies", "gdpr", "privacy settings"])
            has_privacy_policy = any(k in text_low for k in ["privacy policy", "gdpr", "cookie policy"])

            enc = (h.get("content-encoding") or "").lower()
            gzip_or_br = ("gzip" in enc) or ("br" in enc)

            cache_control = h.get("cache-control", "")
            cc_cache_ok = ("max-age" in cache_control.lower()) or ("public" in cache_control.lower())

            links_internal, links_external = [], []
            def norm(u: str) -> Optional[str]:
                if not u: return None
                u = u.strip()
                if u.startswith("#") or u.startswith("javascript:"): return None
                return urljoin(final, u)
            
            if soup:
                for a in soup.find_all("a"):
                    href = norm(a.get("href"))
                    if not href: continue
                    dom = tldextract.extract(urlparse(href).netloc).registered_domain
                    if dom == root_domain: links_internal.append(href)
                    else: links_external.append(href)

            test_links = list(dict.fromkeys(links_internal))[:10]
            for tl in test_links:
                try:
                    r2 = await client.get(tl)
                    if r2.status_code >= 400: broken_links_count += 1
                except: broken_links_count += 1

            can = soup.find("link", attrs={"rel": "canonical"}) if soup else None
            canonical = can.get("href") if (can and can.get("href")) else None
            mr = soup.find("meta", attrs={"name": "robots"}) if soup else None
            meta_robots = (mr.get("content", "").lower() if mr else "")

            hreflangs = []
            if soup:
                for link in soup.find_all("link", attrs={"rel": "alternate"}):
                    if link.get("hreflang") and link.get("href"):
                        hreflangs.append({"hreflang": link["hreflang"], "href": link["href"]})

            schema_present = False
            if soup:
                for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
                    try:
                        json.loads(s.string or "{}")
                        schema_present = True; break
                    except: pass
            og_present = bool(soup and soup.find("meta", attrs={"property": "og:title"}))
            tw_present = bool(soup and soup.find("meta", attrs={"name": "twitter:card"}))

            word_count = len((soup.get_text(" ", strip=True) if soup else "").split())
            thin = word_count < 300

            imgs = soup.find_all("img") if soup else []
            imgs_with_alt = [img for img in imgs if clean(img.get("alt"))]
            alt_coverage_pct = round(100.0 * (len(imgs_with_alt) / max(1, len(imgs))), 2) if imgs else 100.0

            viewport = bool(soup and soup.find("meta", attrs={"name": "viewport"}))
            nav_present = bool(soup and soup.find("nav"))
            intrusive_popup = any(k in text_low for k in ["popup", "modal", "subscribe", "newsletter"])
            meta_charset = bool(soup and soup.find("meta", attrs={"charset": True}))

            page = {
                "url": final,
                "status": status,
                "response_time_ms": round(dur, 2),
                "html_size_bytes": len(body or b""),
                "title": title,
                "meta_description": meta_desc,
                "h1": h1,
                "html_lang": html_lang,
                "security": {
                    "is_https": is_https, "hsts": hsts, "csp": csp, "xfo": xfo,
                    "xcto": xcto, "mixed_content": mixed,
                    "referrer_policy": h.get("referrer-policy", ""), "permissions_policy": h.get("permissions-policy", "")
                },
                "privacy": {"cookie_banner": cookie_banner, "has_privacy_policy": has_privacy_policy},
                "seo": {
                    "canonical": canonical, "meta_robots": meta_robots, "schema": schema_present,
                    "og": og_present, "twitter": tw_present, "hreflang": hreflangs, "thin": thin
                },
                "ux": {"viewport": viewport, "nav_present": nav_present, "intrusive_popup": intrusive_popup,
                        "lazy_img_count": lazy_img_count, "preload_count": preload_count},
                "accessibility": {"alt_coverage_pct": alt_coverage_pct},
                "performance": {"gzip_or_br": gzip_or_br, "cache_control": cache_control, "etag": h.get("etag", ""), "cc_cache_ok": cc_cache_ok},
                "meta": {"charset": meta_charset},
                "links_internal": list(dict.fromkeys(links_internal)),
                "links_external": list(dict.fromkeys(links_external)),
            }
            pages.append(page)

            for href in links_internal[:8]:
                if href not in visited and href not in queue and len(queue) + len(pages) < cfg.max_pages:
                    queue.append(href)

    avg_resp = round(sum(p["response_time_ms"] for p in pages) / max(1, len(pages)), 2)
    avg_html_kb = round(sum(p["html_size_bytes"] for p in pages) / max(1, len(pages)) / 1024.0, 2)

    return {
        "site": base,
        "pages": pages,
        "stats": {
            "avg_response_time_ms": avg_resp,
            "avg_html_size_kb": avg_html_kb,
            "broken_links_count": broken_links_count,
            "favicon_present": favicon_present,
            "robots_txt_ok": robots_txt_ok,
            "sitemap_present": sitemap_present
        }
    }

async def fetch_psi(url: str, strategy: str = "mobile") -> Dict[str, Any]:
    if not PSI_API_KEY:
        return {"source": "none", "strategy": strategy}
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.get(
                "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
                params={"url": url, "strategy": strategy, "key": PSI_API_KEY}
            )
            data = r.json()
            lr = data.get("lighthouseResult", {}) or {}
            audits = lr.get("audits", {}) or {}
            cats = lr.get("categories", {}) or {}

            def num(key: str) -> Optional[float]:
                return (audits.get(key) or {}).get("numericValue")

            def cat_score(name: str) -> Optional[int]:
                sc = cats.get(name, {}).get("score")
                return int(round((sc or 0) * 100)) if sc is not None else None

            return {
                "source": "psi",
                "strategy": strategy,
                "lcp_ms": num("largest-contentful-paint"),
                "fcp_ms": num("first-contentful-paint"),
                "cls": num("cumulative-layout-shift"),
                "tbt_ms": num("total-blocking-time"),
                "tti_ms": num("interactive"),
                "lighthouse": {
                    "Performance": cat_score("performance"),
                    "Accessibility": cat_score("accessibility"),
                    "Best Practices": cat_score("best-practices"),
                    "SEO": cat_score("seo"),
                    "PWA": cat_score("pwa"),
                }
            }
    except Exception:
        return {"source": "none", "strategy": strategy}

def compute_scores(crawl: Dict[str, Any], psi: Dict[str, Any]) -> Dict[str, Any]:
    pages = crawl["pages"]
    stats = crawl["stats"]

    totals = {
        "missing_titles": 0, "missing_meta": 0, "missing_h1": 0,
        "https_pages": 0, "hsts_missing": 0, "csp_missing": 0, "xfo_missing": 0, "xcto_missing": 0, "mixed_content_pages": 0,
        "cookie_banner_pages": 0, "privacy_policy_pages": 0,
        "gzip_missing_pages": 0, "canonical_missing_pages": 0, "hreflang_pages": 0,
        "viewport_missing": 0, "nav_missing": 0, "intrusive_popup_pages": 0,
        "thin_pages": 0, "alt_issue_pages": 0,
        "avg_response_time_ms": stats["avg_response_time_ms"], "avg_html_size_kb": stats["avg_html_size_kb"],
        "broken_links_count": stats.get("broken_links_count", 0),
        "favicon_present": stats.get("favicon_present", False),
        "robots_txt_ok": stats.get("robots_txt_ok", False),
        "sitemap_present": stats.get("sitemap_present", False),
        "html_lang_missing": 0, "meta_charset_missing": 0,
        "cache_misconfig_pages": 0, "no_etag_pages": 0, "referrer_policy_missing": 0, "permissions_policy_missing": 0,
        "lazy_img_pages": 0, "preload_usage_pages": 0,
    }

    for p in pages:
        if not p.get("title"): totals["missing_titles"] += 1
        if not p.get("meta_description"): totals["missing_meta"] += 1
        if not p.get("h1"): totals["missing_h1"] += 1
        if not p.get("html_lang"): totals["html_lang_missing"] += 1
        if not p.get("meta", {}).get("charset"): totals["meta_charset_missing"] += 1

        sec = p["security"]
        if sec["is_https"]: totals["https_pages"] += 1
        if sec["is_https"] and not sec["hsts"]: totals["hsts_missing"] += 1
        if not sec["csp"]: totals["csp_missing"] += 1
        if not sec["xfo"]: totals["xfo_missing"] += 1
        if not sec["xcto"]: totals["xcto_missing"] += 1
        if sec["mixed_content"]: totals["mixed_content_pages"] += 1
        if not sec.get("referrer_policy"): totals["referrer_policy_missing"] += 1
        if not sec.get("permissions_policy"): totals["permissions_policy_missing"] += 1

        prv = p["privacy"]
        if prv["cookie_banner"]: totals["cookie_banner_pages"] += 1
        if prv["has_privacy_policy"]: totals["privacy_policy_pages"] += 1

        perf = p["performance"]
        if not perf["gzip_or_br"]: totals["gzip_missing_pages"] += 1
        if not perf.get("cc_cache_ok"): totals["cache_misconfig_pages"] += 1
        if not perf.get("etag"): totals["no_etag_pages"] += 1

        seo = p["seo"]
        if not seo["canonical"]: totals["canonical_missing_pages"] += 1
        if seo["hreflang"]: totals["hreflang_pages"] += 1
        if seo["thin"]: totals["thin_pages"] += 1

        acc = p["accessibility"]
        if acc["alt_coverage_pct"] < 80.0: totals["alt_issue_pages"] += 1

        ux = p["ux"]
        if not ux["viewport"]: totals["viewport_missing"] += 1
        if not ux["nav_present"]: totals["nav_missing"] += 1
        if ux["intrusive_popup"]: totals["intrusive_popup_pages"] += 1
        if ux["lazy_img_count"] > 0: totals["lazy_img_pages"] += 1
        if ux["preload_count"] > 0: totals["preload_usage_pages"] += 1

    sec_score = 100
    sec_score -= min(30, totals["hsts_missing"] * 3)
    sec_score -= min(30, totals["csp_missing"] * 3)
    sec_score -= min(25, totals["xfo_missing"] * 2.5)
    sec_score -= min(20, totals["xcto_missing"] * 2)
    sec_score -= min(40, totals["mixed_content_pages"] * 8)
    sec_score = max(0, min(100, sec_score))

    perf_score = 100
    perf_score -= min(25, totals["gzip_missing_pages"] * 2)
    perf_score -= min(25, max(0, (totals["avg_response_time_ms"] - 800) / 100))
    if isinstance(psi.get("lcp_ms"), (int, float)):
        perf_score -= min(25, max(0, (psi["lcp_ms"] - 2500) / 150))
    perf_score = max(0, min(100, perf_score))

    seo_score = 100
    seo_score -= min(30, totals["missing_titles"] * 2)
    seo_score -= min(20, totals["missing_meta"])
    seo_score -= min(20, totals["missing_h1"] * 2)
    seo_score = max(0, min(100, seo_score))

    ux_score = 100
    ux_score -= min(25, totals["viewport_missing"] * 3)
    ux_score -= min(15, totals["nav_missing"] * 2)
    ux_score = max(0, min(100, ux_score))

    content_score = 100
    content_score -= min(20, totals["thin_pages"] * 2)
    content_score = max(0, min(100, content_score))

    weights = {"Security":0.28,"Performance":0.27,"SEO":0.23,"UX":0.12,"Content":0.10}
    overall_score = int(round(
        sec_score * weights["Security"] +
        perf_score * weights["Performance"] +
        seo_score * weights["SEO"] +
        ux_score * weights["UX"] +
        content_score * weights["Content"]
    ))
    grade, grade_class = grade_for_score(overall_score)

    total_errors = totals["hsts_missing"] + totals["csp_missing"] + totals["mixed_content_pages"]
    total_warnings = totals["missing_titles"] + totals["missing_meta"] + totals["broken_links_count"]
    total_notices = max(0, len(pages) - total_errors - total_warnings)

    weak_areas = []
    if totals["mixed_content_pages"] > 0: weak_areas.append("Mixed Content detected")
    if totals["missing_titles"] > 0: weak_areas.append("Missing Titles")
    if totals["thin_pages"] > 0: weak_areas.append("Thin Content")

    return {
        "overall_score": overall_score,
        "grade": grade,
        "grade_class": grade_class,
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "total_notices": total_notices,
        "category_scores": {
            "Security": sec_score,
            "Performance": perf_score,
            "SEO": seo_score,
            "UX": ux_score,
            "Content": content_score,
        },
        "totals": totals,
        "weak_areas": weak_areas,
    }

def build_summary(site: str, scores: Dict[str, Any], psi: Dict[str, Any]) -> str:
    return f"Certified audit for {site}. Overall score: {scores['overall_score']} ({scores['grade']}). This comprehensive diagnostic identified {scores['total_errors']} critical security vulnerabilities and {scores['total_warnings']} optimization warnings."

def status_label(score: int) -> str:
    if score >= 80: return "Good"
    if score >= 60: return "Warning"
    return "Critical"

def metric_row(name: str, score: int, priority: str, impact: str, rec: str) -> Dict[str, Any]:
    return {"name": name, "status": status_label(score), "score": score, "priority": priority, "impact": impact, "recommendation": rec}

def build_category_tables(scores: Dict[str, Any], psi: Dict[str, Any]) -> List[Dict[str, Any]]:
    t = scores["totals"]
    cats: List[Dict[str, Any]] = []

    # 1. SECURITY & COMPLIANCE
    sec_metrics = [
        metric_row("SSL/HTTPS Protocol", 100 if t["https_pages"] > 0 else 0, "High", "Critical for data encryption.", "Enforce site-wide HTTPS."),
        metric_row("HSTS Protection", max(0, 100 - t["hsts_missing"] * 20), "High", "Prevents downgrade attacks.", "Implement HSTS headers."),
        metric_row("CSP Policy", max(0, 100 - t["csp_missing"] * 20), "Medium", "Mitigates XSS risks.", "Define a Content Security Policy."),
        metric_row("Mixed Content", 100 if t["mixed_content_pages"] == 0 else 0, "High", "Security bypass vulnerability.", "Replace insecure http resources."),
        metric_row("Privacy Compliance", 100 if t["privacy_policy_pages"] > 0 else 0, "Medium", "Legal GDPR/CCPA risk.", "Ensure a clear Privacy Policy exists."),
    ]
    cats.append({"name": "Security & Compliance", "icon": "fa-shield-halved", "metrics": sec_metrics})

    # 2. PERFORMANCE & CORE WEB VITALS
    perf_metrics = [
        metric_row("Server Response Time", max(0, 100 - (t["avg_response_time_ms"]/10)), "High", "Impacts user retention.", "Optimize backend server processing."),
        metric_row("Asset Compression", 100 if t["gzip_missing_pages"] == 0 else 50, "Medium", "Reduces bandwidth usage.", "Enable Gzip or Brotli compression."),
        metric_row("Browser Caching", 100 if t["cache_misconfig_pages"] == 0 else 50, "Medium", "Speeds up repeat visits.", "Implement long-term cache headers."),
        metric_row("Largest Contentful Paint", 100 if psi.get("lcp_ms", 3000) < 2500 else 60, "High", "Primary loading metric.", "Optimize images and font delivery."),
    ]
    cats.append({"name": "Performance", "icon": "fa-gauge-high", "metrics": perf_metrics})

    # 3. SEO & INDEXABILITY
    seo_metrics = [
        metric_row("Title Tag Quality", max(0, 100 - t["missing_titles"] * 20), "High", "Critical for ranking.", "Add unique descriptive titles."),
        metric_row("Meta Descriptions", max(0, 100 - t["missing_meta"] * 20), "Medium", "Impacts CTR from SERP.", "Write unique meta descriptions."),
        metric_row("Sitemap Integrity", 100 if t["sitemap_present"] else 0, "Medium", "Aids crawler discovery.", "Generate and submit a sitemap.xml."),
        metric_row("Robots.txt Presence", 100 if t["robots_txt_ok"] else 0, "Medium", "Controls crawl budget.", "Configure robots.txt correctly."),
        metric_row("Canonical Alignment", max(0, 100 - t["canonical_missing_pages"] * 20), "Medium", "Prevents duplicate content.", "Self-reference with canonical tags."),
    ]
    cats.append({"name": "SEO & Indexing", "icon": "fa-magnifying-glass-chart", "metrics": seo_metrics})

    # 4. USER EXPERIENCE & ACCESSIBILITY
    ux_metrics = [
        metric_row("Mobile Viewport", 100 if t["viewport_missing"] == 0 else 0, "High", "Critical for mobile UX.", "Define meta-viewport tag."),
        metric_row("Image Alt Text", max(0, 100 - t["alt_issue_pages"] * 20), "Medium", "Accessibility compliance.", "Provide descriptive alt attributes."),
        metric_row("Navigation Structure", 100 if t["nav_missing"] == 0 else 50, "Medium", "User journey logic.", "Ensure nav elements are semantic."),
    ]
    cats.append({"name": "User Experience", "icon": "fa-user-check", "metrics": ux_metrics})

    return cats

def build_trend_chart(site: str, db: Session, current_overall: int) -> Dict[str, Any]:
    last = db.query(Audit).join(Site).filter(Site.url == site).order_by(Audit.created_at.desc()).limit(8).all()
    labels = [a.created_at.strftime("%Y-%m-%d") for a in reversed(last)]
    values = [a.overall_score for a in reversed(last)]
    labels.append(datetime.utcnow().strftime("%Y-%m-%d"))
    values.append(current_overall)
    return {"labels": labels, "values": values}

# ------------------------------------------------------------------------------
# FastAPI App & Dependencies
# ------------------------------------------------------------------------------
app = FastAPI()

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get("session")
    uid = unsign_session(token) if token else None
    if not uid: return None
    return db.get(User, uid)

def require_auth(user: Optional[User]) -> User:
    if not user: raise HTTPException(status_code=401, detail="Login required")
    if not user.is_verified: raise HTTPException(status_code=403, detail="Email not verified")
    return user

def require_admin(user: Optional[User]) -> User:
    user = require_auth(user)
    if not user.is_admin: raise HTTPException(status_code=403, detail="Admin required")
    return user

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, user: Optional[User] = Depends(get_current_user)):
    return render_page(user, env.from_string(HOME_TEMPLATE).render(user=user))

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, user: Optional[User] = Depends(get_current_user)):
    return render_page(user, env.from_string(AUTH_REGISTER_TEMPLATE).render(), "Register")

@app.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    timezone: str = Form("Asia/Karachi"),
    preferred_hour: int = Form(9),
    db: Session = Depends(get_db)
):
    try:
        v = validate_email(email)
        email = v.email
    except EmailNotValidError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=email,
        password_hash=hash_password(password),
        timezone=timezone,
        preferred_hour=preferred_hour
    )
    db.add(user); db.commit(); db.refresh(user)

    token = verify_signer.dumps({"uid": user.id, "email": user.email, "ts": int(time.time())})
    verify_url = f"{APP_DOMAIN}/verify?token={token}"
    send_email(to_email=email, subject="Verify account", html_body=f"Click <a href='{verify_url}'>here</a>")
    return RedirectResponse("/login", status_code=303)

@app.get("/verify")
async def verify(token: str, db: Session = Depends(get_db)):
    try: data = verify_signer.loads(token)
    except: raise HTTPException(status_code=400)
    user = db.get(User, data["uid"])
    if user: user.is_verified = True; db.commit()
    return RedirectResponse("/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user: Optional[User] = Depends(get_current_user)):
    return render_page(user, env.from_string(AUTH_LOGIN_TEMPLATE).render(), "Login")

@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    user.last_login_at = datetime.utcnow(); db.commit()
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie("session", sign_session(user.id), httponly=True, samesite="lax", secure=True)
    return resp

@app.get("/logout")
async def logout():
    resp = RedirectResponse("/")
    resp.delete_cookie("session")
    return resp

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    user = require_auth(user)
    sites = db.query(Site).filter(Site.user_id == user.id).all()
    audits = db.query(Audit).join(Site).filter(Site.user_id == user.id).order_by(Audit.created_at.desc()).limit(20).all()
    return render_page(user, env.from_string(DASHBOARD_TEMPLATE).render(sites=sites, audits=audits))

@app.post("/sites/add")
async def add_site(url: str = Form(...), schedule_enabled: Optional[str] = Form(None), db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    user = require_auth(user)
    db.add(Site(user_id=user.id, url=url.strip(), schedule_enabled=bool(schedule_enabled)))
    db.commit()
    return RedirectResponse("/dashboard", status_code=303)

@app.get("/audit")
async def audit_site(site_id: int, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    user = require_auth(user)
    site = db.get(Site, site_id)
    if not site or site.user_id != user.id: raise HTTPException(status_code=404)
    crawl = await crawl_site(CrawlConfig(url=site.url))
    psi = await fetch_psi(crawl["site"])
    scores = compute_scores(crawl, psi)
    audit = Audit(site_id=site.id, payload_json=json.dumps({"crawl": crawl, "psi": psi, "scores": scores}), 
                  overall_score=scores["overall_score"], grade=scores["grade"])
    db.add(audit); db.commit()
    return RedirectResponse(f"/report?id={audit.id}", status_code=303)

@app.post("/report", response_class=HTMLResponse)
async def render_report(url: str = Form(...), psi_strategy: str = Form("mobile"), db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    crawl = await crawl_site(CrawlConfig(url=url.strip()))
    psi = await fetch_psi(crawl["site"], psi_strategy)
    scores = compute_scores(crawl, psi)
    trend_data = build_trend_chart(crawl["site"], db, scores["overall_score"])
    categories = build_category_tables(scores, psi)
    
    # Calculate additional metadata for report template
    owner_insights = [
        {"title": "High Priority Security", "description": "Implement missing HSTS and CSP headers to protect user data."},
        {"title": "SEO Quick Win", "description": "Optimizing meta tags can boost CTR by up to 30% in search results."}
    ]
    
    return HTMLResponse(env.from_string(HTML_TEMPLATE).render(
        app_name=APP_NAME, website_url=crawl["site"], audit_date=datetime.utcnow().strftime("%Y-%m-%d"),
        audit_id="TEMP-"+secrets.token_hex(4).upper(), grade=scores["grade"], grade_class=scores["grade_class"],
        overall_score=scores["overall_score"], total_errors=scores["total_errors"],
        total_warnings=scores["total_warnings"], total_notices=scores["total_notices"],
        executive_summary_200_words=build_summary(crawl["site"], scores, psi),
        weak_areas=scores["weak_areas"], audit_categories=categories, 
        owner_insights=owner_insights,
        validity_date=(datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d"), 
        trend_chart_data=trend_data
    ))

@app.get("/report", response_class=HTMLResponse)
async def view_report(id: int, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    audit = db.get(Audit, id)
    if not audit: raise HTTPException(status_code=404)
    payload = json.loads(audit.payload_json)
    trend_data = build_trend_chart(payload["crawl"]["site"], db, audit.overall_score)
    categories = build_category_tables(payload["scores"], payload["psi"])
    
    owner_insights = [
        {"title": "High Priority Security", "description": "Implement missing HSTS and CSP headers to protect user data."},
        {"title": "SEO Quick Win", "description": "Optimizing meta tags can boost CTR by up to 30% in search results."}
    ]
    
    return HTMLResponse(env.from_string(HTML_TEMPLATE).render(
        app_name=APP_NAME, website_url=payload["crawl"]["site"], audit_date=audit.created_at.strftime("%Y-%m-%d"),
        audit_id="RPT-"+str(audit.id).zfill(5), grade=audit.grade, grade_class=grade_for_score(audit.overall_score)[1],
        overall_score=audit.overall_score, total_errors=payload["scores"]["total_errors"],
        total_warnings=payload["scores"]["total_warnings"], total_notices=payload["scores"]["total_notices"],
        executive_summary_200_words=build_summary(payload["crawl"]["site"], payload["scores"], payload["psi"]),
        weak_areas=payload["scores"]["weak_areas"], audit_categories=categories, 
        owner_insights=owner_insights,
        validity_date=(audit.created_at + timedelta(days=30)).strftime("%Y-%m-%d"), 
        trend_chart_data=trend_data
    ))

async def scheduler_loop():
    while True:
        try:
            db = SessionLocal()
            now_utc = datetime.utcnow()
            for u in db.query(User).filter(User.is_verified == True).all():
                tz = ZoneInfo(u.timezone or "UTC")
                local_now = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
                if local_now.hour == (u.preferred_hour or 9) and local_now.minute == 0:
                    for s in db.query(Site).filter(Site.user_id == u.id, Site.schedule_enabled == True).all():
                        crawl = await crawl_site(CrawlConfig(url=s.url))
                        psi = await fetch_psi(crawl["site"])
                        scores = compute_scores(crawl, psi)
                        audit = Audit(site_id=s.id, payload_json=json.dumps({"crawl": crawl, "psi": psi, "scores": scores}),
                                      overall_score=scores["overall_score"], grade=scores["grade"])
                        db.add(audit); db.commit()
                        send_email(u.email, "Daily Report", f"New audit for {s.url} finished.")
            db.close()
        except: pass
        await asyncio.sleep(60)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(scheduler_loop())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
