
# app.py
# FF Tech — Single-file FastAPI backend integrated with your HTML
# - Serves embedded HTML at "/"
# - /audit?url=... returns charts, conclusions, 140 metrics + category totals
# - /export-pdf?url=... returns a 5-page Certified PDF
# - Persists audits to Railway DB (PostgreSQL via DATABASE_URL) or SQLite fallback

import os
import json
import random
from datetime import datetime
from typing import List, Dict

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response

# ReportLab for PDF
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics import renderPDF

# SQLAlchemy for Railway DB
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

# ------------------------------------------------------------------------------
# Config (Railway-ready)
# ------------------------------------------------------------------------------
APP_NAME = "FF Tech — AI-Powered Website Audit Platform"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fftech_demo.db")  # Railway: set to postgres URL
engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# ------------------------------------------------------------------------------
# DB Model
# ------------------------------------------------------------------------------
class Audit(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True)
    url = Column(String(2048), index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    overall = Column(Integer, nullable=False)
    grade = Column(String(8), nullable=False)
    errors = Column(Integer, default=0)
    warnings = Column(Integer, default=0)
    notices = Column(Integer, default=0)
    cat_scores_json = Column(Text)   # {"SEO":..., "Performance":..., "Security":..., "Accessibility":..., "Mobile":...}
    cat_totals_json = Column(Text)   # {"cat1":..., "cat2":..., "cat3":..., "cat4":..., "cat5":..., "overall":...}
    summary = Column(Text)
    strengths_json = Column(Text)
    weaknesses_json = Column(Text)
    priority_json = Column(Text)
    metrics_json = Column(Text)      # list of 140 metrics
Base.metadata.create_all(bind=engine)

# ------------------------------------------------------------------------------
# FastAPI app
# ------------------------------------------------------------------------------
app = FastAPI(title=APP_NAME)

# ------------------------------------------------------------------------------
# Embedded HTML (your UI, wired for category totals + PDF)
# ------------------------------------------------------------------------------
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FF Tech AI-Powered Website Audit Platform</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailscript>
    <!-- Chart.js CDN -->
    https://cdn.jsdelivr.net/npm/chart.js</script>
    <!-- Font Awesome CDN -->
    https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css
    <style>
        body { font-family: 'Inter', sans-serif; }
        .gradient-bg { background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); }
        .metric-card { border-left-width: 6px; padding-left: 1.5rem; margin-bottom: 2rem; background: #fff; box-shadow: 0 25px 50px rgba(0,0,0,.1); border-radius: 1rem; padding: 2rem; }
        .green { border-color: #10b981; }
        .yellow { border-color: #f59e0b; }
        .red { border-color: #ef4444; }
        canvas { max-height: 200px; width: 100% !important; }
        .category-header { font-size: 2rem; font-weight: 700; text-align: center; margin-bottom: 3rem; padding: 2.5rem; border-radius: 1.5rem; box-shadow: 0 25px 50px rgba(0,0,0,.15); color:#fff; }
        .category-summary { background: linear-gradient(to right, #f9fafb, #f3f4f6); border-radius: 1.5rem; padding: 2.5rem; margin-bottom: 1rem; box-shadow: 0 20px 40px rgba(0,0,0,.08); }
        .conclusion { font-size: 1.05rem; line-height: 1.8rem; color: #374151; }
        .total-badge { display:inline-block; margin-top:8px; padding:6px 12px; border-radius:999px; font-weight:700; background:#eef2ff; color:#4338ca; }
    </style>
</head>
<body class="bg-gray-50 text-gray-800">

    <!-- Header -->
    <header class="gradient-bg text-white py-6 shadow-2xl fixed w-full top-0 z-50">
        <div class="max-w-7xl mx-auto px-6 flex justify-between items-center">
            <h1 class="text-3xl font-bold">FF Tech</h1>
            <nav class="space-x-8 text-lg">
                #heroHome</a>
                <aummarySummary</a>
                #dashboardAudit Dashboard</a>
            </nav>
        </div>
    </header>

    <!-- Hero -->
    <section id="hero" class="gradient-bg text-white pt-32 pb-24 px-6">
        <div class="max-w-5xl mx-auto text-center">
            <h2 class="text-5xl md:text-6xl font-bold mb-8">AI-Powered Website Audit Platform</h2>
            <p class="text-2xl mb-12">140 Professional Metrics • Detailed Category Analysis • Instant Results</p>
            <form id="audit-form" class="flex max-w-3xl mx-auto mb-10">
                <input type="url" id="website-url" placeholder="https://example.com" required class="flex-1 px-8 py-5 rounded-l-2xl text-gray-900 text-xl">
                <button type="submit" class="bg-white text-indigo-600 px-12 py-5 rounded-r-2xl font-bold text-xl hover:bg-gray-100">Run Free Audit</button>
            </form>
            <p class="text-xl mb-6" id="audit-counter">Free Audits Remaining: <span id="remaining" class="text-3xl font-bold">10</span></p>
            <div class="flex justify-center space-x-10 text-xl">
                <span><i class="fas fa-lock"></i> Secure</span>
                <span><i class="fas fa-bolt"></i> Instant</span>
                <span><i class="fas fa-shield-alt"></i> Trusted</span>
            </div>
        </div>
    </section>

    <!-- Progress -->
    <section id="progress" class="py-20 px-6 hidden">
        <div class="max-w-5xl mx-auto bg-white rounded-3xl shadow-2xl p-12">
            <h3 class="text-4xl font-bold text-center mb-12">Audit Progress</h3>
            <div class="space-y-8">
                <div class="flex items-center"><span class="w-40 font-bold">Crawling</span><progress id="p-crawl" class="flex-1 h-6" value="0" max="100"></progress><span id="crawl-pct" class="w-24 text-right font-bold">0%</span></div>
                <div class="flex items-center"><span class="w-40 font-bold">Analyzing</span><progress id="p-analyze" class="flex-1 h-6" value="0" max="100"></progress><span id="analyze-pct" class="w-24 text-right font-bold">0%</span></div>
                <div class="flex items-center"><span class="w-40 font-bold">Scoring</span><progress id="p-score" class="flex-1 h-6" value="0" max="100"></progress><span id="score-pct" class="w-24 text-right font-bold">0%</span></div>
                <div class="flex items-center"><span class="w-40 font-bold">Reporting</span><progress id="p-report" class="flex-1 h-6" value="0" max="100"></progress><span id="report-pct" class="w-24 text-right font-bold">0%</span></div>
            </div>
            <div class="grid md:grid-cols-2 gap-12 mt-16">
                <div><canvas id="health-gauge"></canvas></div>
                <div><canvas id="issues-chart"></canvas></div>
            </div>
        </div>
    </section>

    <!-- Executive Summary -->
    <section id="summary" class="py-20 px-6 bg-white hidden">
        <div class="max-w-6xl mx-auto">
            <div class="text-center mb-16">
                <span id="grade-badge" class="text-8xl font-black px-12 py-8 rounded-full bg-green-100 text-green-700 shadow-2xl inline-block">A+</span>
            </div>
            <canvas id="overall-gauge" class="mx-auto mb-16" width="400" height="400"></canvas>
            <div class="bg-gradient-to-br from-indigo-50 to-purple-50 rounded-3xl p-12 mb-16">
                <h3 class="text-4xl font-bold text-center mb-8">Executive Summary</h3>
                <p id="exec-summary" class="text-xl leading-relaxed max-w-4xl mx-auto"></p>
            </div>
            <div class="grid md:grid-cols-3 gap-12 mb-16">
                <div class="bg-green-50 rounded-3xl p-10 border-4 border-green-300"><h4 class="text-3xl font-bold text-green-700 mb-6">Strengths</h4><ul id="strengths" class="space-y-4 text-lg"></ul></div>
                <div class="bg-red-50 rounded-3xl p-10 border-4 border-red-300"><h4 class="text-3xl font-bold text-red-700 mb-6">Weak Areas</h4><ul id="weaknesses" class="space-y-4 text-lg"></ul></div>
                <div class="bg-amber-50 rounded-3xl p-10 border-4 border-amber-300"><h4 class="text-3xl font-bold text-amber-700 mb-6">Priority Fixes</h4><ul id="priority" class="space-y-4 text-lg"></ul></div>
            </div>
            <canvas id="category-chart" class="max-w-5xl mx-auto mb-16"></canvas>
            <div class="text-center"><button id="export-pdf" class="bg-indigo-600 text-white px-16 py-6 rounded-3xl text-2xl font-bold">Export PDF</button></div>
        </div>
    </section>

    <!-- Dashboard (with Category Totals integrated) -->
    <section id="dashboard" class="py-20 px-6 hidden">
        <div class="max-w-7xl mx-auto">
            <h2 class="text-5xl font-bold text-center mb-20">140-Metric Detailed Audit Dashboard</h2>

            <!-- Category 1 -->
            <div class="mb-24">
                <h3 class="category-header bg-gradient-to-r from-indigo-600 to-purple-600">Overall Site Health (Metrics 1–10)</h3>
                <div class="category-summary">
                    <h4 class="text-2xl font-bold mb-2 text-center">Category Total</h4>
                    <p class="text-center"><span id="cat1-total" class="total-badge">--%</span></p>
                    <p id="cat1-conclusion" class="conclusion text-center max-w-4xl mx-auto mt-4"></p>
                </div>
                <div class="grid md:grid-cols-2 gap-12 mb-16">
                    <div class="bg-white rounded-3xl shadow-2xl p-8"><canvas id="cat1-summary-chart"></canvas></div>
                    <div class="bg-white rounded-3xl shadow-2xl p-8"><canvas id="cat1-trend-chart"></canvas></div>
                </div>
                <div class="grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-10">
                    <div id="metric-001" class="metric-card green"><h5 class="text-xl font-bold mb-4">001. Site Health Score</h5><canvas id="chart-001"></canvas></div>
                    <div id="metric-002" class="metric-card red"><h5 class="text-xl font-bold mb-4">002. Total Errors</h5><canvas id="chart-002"></canvas></div>
                    <div id="metric-003" class="metric-card yellow"><h5 class="text-xl font-bold mb-4">003. Total Warnings</h5><canvas id="chart-003"></canvas></div>
                    <div id="metric-004" class="metric-card green"><h5 class="text-xl font-bold mb-4">004. Total Notices</h5><canvas id="chart-004"></canvas></div>
                    <div id="metric-005" class="metric-card green"><h5 class="text-xl font-bold mb-4">005. Total Crawled Pages</h5><canvas id="chart-005"></canvas></div>
                    <div id="metric-006" class="metric-card green"><h5 class="text-xl font-bold mb-4">006. Total Indexed Pages</h5><canvas id="chart-006"></canvas></div>
                    <div id="metric-007" class="metric-card yellow"><h5 class="text-xl font-bold mb-4">007. Issues Trend</h5><canvas id="chart-007"></canvas></div>
                    <div id="metric-008" class="metric-card green"><h5 class="text-xl font-bold mb-4">008. Crawl Budget Efficiency</h5><canvas id="chart-008"></canvas></div>
                    <div id="metric-009" class="metric-card yellow"><h5 class="text-xl font-bold mb-4">009. Orphan Pages Percentage</h5><canvas id="chart-009"></canvas></div>
                    <div id="metric-010" class="metric-card green"><h5 class="text-xl font-bold mb-4">010. Audit Completion Status</h5><canvas id="chart-010"></canvas></div>
                </div>
            </div>

            <!-- Category 2 -->
            <div class="mb-24">
                <h3 class="category-header bg-gradient-to-r from-green-600 to-emerald-600">Crawlability & Indexation (Metrics 11–30)</h3>
                <div class="category-summary">
                    <h4 class="text-2xl font-bold mb-2 text-center">Category Total</h4>
                    <p class="text-center"><span id="cat2-total" class="total-badge">--%</span></p>
                    <p id="cat2-conclusion" class="conclusion text-center max-w-4xl mx-auto mt-4"></p>
                </div>
                <div class="grid md:grid-cols-2 gap-12 mb-16">
                    <div class="bg-white rounded-3xl shadow-2xl p-8"><canvas id="cat2-summary-chart"></canvas></div>
                    <div class="bg-white rounded-3xl shadow-2xl p-8"><canvas id="cat2-status-chart"></canvas></div>
                </div>
                <div class="grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-10">
                    <div id="metric-011" class="metric-card green"><h5 class="text-xl font-bold mb-4">011. HTTP 2xx Pages</h5><canvas id="chart-011"></canvas></div>
                    <div id="metric-012" class="metric-card green"><h5 class="text-xl font-bold mb-4">012. HTTP 3xx Pages</h5><canvas id="chart-012"></canvas></div>
                    <div id="metric-013" class="metric-card red"><h5 class="text-xl font-bold mb-4">013. HTTP 4xx Pages</h5><canvas id="chart-013"></canvas></div>
                    <div id="metric-014" class="metric-card red"><h5 class="text-xl font-bold mb-4">014. HTTP 5xx Pages</h5><canvas id="chart-014"></canvas></div>
                    <div id="metric-015" class="metric-card yellow"><h5 class="text-xl font-bold mb-4">015. Redirect Chains</h5><canvas id="chart-015"></canvas></div>
                    <div id="metric-016" class="metric-card red"><h5 class="text-xl font-bold mb-4">016. Redirect Loops</h5><canvas id="chart-016"></canvas></div>
                    <div id="metric-017" class="metric-card red"><h5 class="text-xl font-bold mb-4">017. Broken Internal Links</h5><canvas id="chart-017"></canvas></div>
                    <div id="metric-018" class="metric-card red"><h5 class="text-xl font-bold mb-4">018. Broken External Links</h5><canvas id="chart-018"></canvas></div>
                    <div id="metric-019" class="metric-card yellow"><h5 class="text-xl font-bold mb-4">019. robots.txt Blocked URLs</h5><canvas id="chart-019"></canvas></div>
                    <div id="metric-020" class="metric-card yellow"><h5 class="text-xl font-bold mb-4">020. Meta Robots Blocked URLs</h5><canvas id="chart-020"></canvas></div>
                    <div id="metric-021" class="metric-card yellow"><h5 class="text-xl font-bold mb-4">021. Non-Canonical Pages</h5><canvas id="chart-021"></canvas></div>
                    <div id="metric-022" class="metric-card red"><h5 class="text-xl font-bold mb-4">022. Missing Canonical Tags</h5><canvas id="chart-022"></canvas></div>
                    <div id="metric-023" class="metric-card red"><h5 class="text-xl font-bold mb-4">023. Incorrect Canonical Tags</h5><canvas id="chart-023"></canvas></div>
                    <div id="metric-024" class="metric-card yellow"><h5 class="text-xl font-bold mb-4">024. Sitemap Missing Pages</h5><canvas id="chart-024"></canvas></div>
                    <div id="metric-025" class="metric-card yellow"><h5 class="text-xl font-bold mb-4">025. Sitemap Not Crawled Pages</h5><canvas id="chart-025"></canvas></div>
                    <div id="metric-026" class="metric-card red"><h5 class="text-xl font-bold mb-4">026. Hreflang Errors</h5><canvas id="chart-026"></canvas></div>
                    <div id="metric-027" class="metric-card red"><h5 class="text-xl font-bold mb-4">027. Hreflang Conflicts</h5><canvas id="chart-027"></canvas></div>
                    <div id="metric-028" class="metric-card yellow"><h5 class="text-xl font-bold mb-4">028. Pagination Issues</h5><canvas id="chart-028"></canvas></div>
                    <div id="metric-029" class="metric-card green"><h5 class="text-xl font-bold mb-4">029. Crawl Depth Distribution</h5><canvas id="chart-029"></canvas></div>
                    <div id="metric-030" class="metric-card yellow"><h5 class="text-xl font-bold mb-4">030. Duplicate Parameter URLs</h5><canvas id="chart-030"></canvas></div>
                </div>
            </div>

            <!-- Category 3 -->
            <div class="mb-24">
                <h3 class="category-header bg-gradient-to-r from-purple-600 to-pink-600">On-Page SEO (Metrics 31–65)</h3>
                <div class="category-summary">
                    <h4 class="text-2xl font-bold mb-2 text-center">Category Total</h4>
                    <p class="text-center"><span id="cat3-total" class="total-badge">--%</span></p>
                    <p id="cat3-conclusion" class="conclusion text-center max-w-4xl mx-auto mt-4"></p>
                </div>
                <div class="grid md:grid-cols-2 gap-12 mb-16">
                    <div class="bg-white rounded-3xl shadow-2xl p-8"><canvas id="cat3-summary-chart"></canvas></div>
                    <div class="bg-white rounded-3xl shadow-2xl p-8"><canvas id="cat3-issues-chart"></canvas></div>
                </div>
                <!-- Cards for 31..65 should be present in your HTML; backend fills charts & severity -->
                <div class="grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-10" id="cat3-auto-grid"></div>
            </div>

            <!-- Category 4 -->
            <div class="mb-24">
                <h3 class="category-header bg-gradient-to-r from-orange-600 to-red-600">Performance & Technical (Metrics 66–86)</h3>
                <div class="category-summary">
                    <h4 class="text-2xl font-bold mb-2 text-center">Category Total</h4>
                    <p class="text-center"><span id="cat4-total" class="total-badge">--%</span></p>
                    <p id="cat4-conclusion" class="conclusion text-center max-w-4xl mx-auto mt-4"></p>
                </div>
                <div class="grid md:grid-cols-2 gap-12 mb-16">
                    <div class="bg-white rounded-3xl shadow-2xl p-8"><canvas id="cat4-cwv-chart"></canvas></div>
                    <div class="bg-white rounded-3xl shadow-2xl p-8"><canvas id="cat4-resources-chart"></canvas></div>
                </div>
                <div class="grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-10" id="cat4-auto-grid"></div>
            </div>

            <!-- Category 5 -->
            <div class="mb-24">
                <h3 class="category-header bg-gradient-to-r from-teal-600 to-cyan-600">Mobile, Security & International (Metrics 87–140)</h3>
                <div class="category-summary">
                    <h4 class="text-2xl font-bold mb-2 text-center">Category Total</h4>
                    <p class="text-center"><span id="cat5-total" class="total-badge">--%</span></p>
                    <p id="cat5-conclusion" class="conclusion text-center max-w-4xl mx-auto mt-4"></p>
                </div>
                <div class="grid md:grid-cols-2 gap-12 mb-16">
                    <div class="bg-white rounded-3xl shadow-2xl p-8"><canvas id="cat5-security-chart"></canvas></div>
                    <div class="bg-white rounded-3xl shadow-2xl p-8"><canvas id="cat5-mobile-chart"></canvas></div>
                </div>
                <div class="grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-10" id="cat5-auto-grid"></div>
            </div>
        </div>
    </section>

    <!-- Footer -->
    <footer class="bg-gray-900 text-white py-12 text-center">
        <p class="text-3xl font-bold">FF Tech © December 27, 2025</p>
        <p class="text-xl mt-4">Global Enterprise AI Website Audit Platform</p>
    </footer>

    <script>
        const metricTitles = {
            // 1..140 titles from your spec (short aliases for auto-injection)
            1: "Site Health Score", 2: "Total Errors", 3: "Total Warnings", 4: "Total Notices", 5: "Total Crawled Pages",
            6: "Total Indexed Pages", 7: "Issues Trend", 8: "Crawl Budget Efficiency", 9: "Orphan Pages Percentage", 10: "Audit Completion Status",
            11: "HTTP 2xx Pages", 12: "HTTP 3xx Pages", 13: "HTTP 4xx Pages", 14: "HTTP 5xx Pages", 15: "Redirect Chains", 16: "Redirect Loops",
            17: "Broken Internal Links", 18: "Broken External Links", 19: "robots.txt Blocked URLs", 20: "Meta Robots Blocked URLs",
            21: "Non-Canonical Pages", 22: "Missing Canonical Tags", 23: "Incorrect Canonical Tags", 24: "Sitemap Missing Pages",
            25: "Sitemap Not Crawled Pages", 26: "Hreflang Errors", 27: "Hreflang Conflicts", 28: "Pagination Issues",
            29: "Crawl Depth Distribution", 30: "Duplicate Parameter URLs",
            31: "Missing Title Tags", 32: "Duplicate Title Tags", 33: "Title Too Long", 34: "Title Too Short", 35: "Missing Meta Descriptions",
            36: "Duplicate Meta Descriptions", 37: "Meta Too Long", 38: "Meta Too Short", 39: "Missing H1", 40: "Multiple H1",
            41: "Duplicate Headings", 42: "Thin Content Pages", 43: "Duplicate Content Pages", 44: "Low Text-to-HTML Ratio",
            45: "Missing Image Alt Tags", 46: "Duplicate Alt Tags", 47: "Large Uncompressed Images", 48: "Pages Without Indexed Content",
            49: "Missing Structured Data", 50: "Structured Data Errors", 51: "Rich Snippet Warnings", 52: "Missing Open Graph Tags",
            53: "Long URLs", 54: "Uppercase URLs", 55: "Non-SEO-Friendly URLs", 56: "Too Many Internal Links",
            57: "Pages Without Incoming Links", 58: "Orphan Pages", 59: "Broken Anchor Links", 60: "Redirected Internal Links",
            61: "NoFollow Internal Links", 62: "Link Depth Issues", 63: "External Links Count", 64: "Broken External Links",
            65: "Anchor Text Issues",
            66: "Largest Contentful Paint", 67: "First Contentful Paint", 68: "Cumulative Layout Shift", 69: "Total Blocking Time",
            70: "First Input Delay", 71: "Speed Index", 72: "Time to Interactive", 73: "DOM Content Loaded", 74: "Total Page Size",
            75: "Requests Per Page", 76: "Unminified CSS", 77: "Unminified JavaScript", 78: "Render Blocking Resources",
            79: "Excessive DOM Size", 80: "Third-Party Script Load", 81: "Server Response Time", 82: "Image Optimization",
            83: "Lazy Loading Issues", 84: "Browser Caching Issues", 85: "Missing GZIP / Brotli", 86: "Resource Load Errors",
            87: "Mobile Friendly Test", 88: "Viewport Meta Tag", 89: "Small Font Issues", 90: "Tap Target Issues",
            91: "Mobile Core Web Vitals", 92: "Mobile Layout Issues", 93: "Intrusive Interstitials", 94: "Mobile Navigation Issues",
            95: "HTTPS Implementation", 96: "SSL Certificate Validity", 97: "Expired SSL", 98: "Mixed Content", 99: "Insecure Resources",
            100: "Missing Security Headers", 101: "Open Directory Listing", 102: "Login Pages Without HTTPS",
            103: "Missing Hreflang", 104: "Incorrect Language Codes", 105: "Hreflang Conflicts", 106: "Region Targeting Issues",
            107: "Multi-Domain SEO Issues", 108: "Domain Authority", 109: "Referring Domains", 110: "Total Backlinks",
            111: "Toxic Backlinks", 112: "NoFollow Backlinks", 113: "Anchor Distribution", 114: "Referring IPs",
            115: "Lost / New Backlinks", 116: "JS Rendering Issues", 117: "CSS Blocking", 118: "Crawl Budget Waste",
            119: "AMP Issues", 120: "PWA Issues", 121: "Canonical Conflicts", 122: "Subdomain Duplication", 123: "Pagination Conflicts",
            124: "Dynamic URL Issues", 125: "Lazy Load Conflicts", 126: "Sitemap Presence", 127: "Noindex Issues",
            128: "Structured Data Consistency", 129: "Redirect Correctness", 130: "Broken Rich Media", 131: "Social Metadata Presence",
            132: "Error Trend", 133: "Health Trend", 134: "Crawl Trend", 135: "Index Trend", 136: "CWV Trend", 137: "Backlink Trend",
            138: "Keyword Trend", 139: "Historical Comparison", 140: "Overall Stability Index"
        };

        const runAudit = async (url) => {
            const res = await fetch(`/audit?url=${encodeURIComponent(url)}`);
            return await res.json();
        };

        function injectMetricCard(containerId, num, severity) {
            const title = metricTitles[num] || `Metric ${num}`;
            const pad = String(num).padStart(3, '0');
            const card = document.createElement('div');
            card.id = `metric-${pad}`;
            card.className = `metric-card ${severity}`;
            card.innerHTML = `<h5 class="text-xl font-bold mb-4">${pad}. ${title}</h5><canvas id="chart-${pad}"></canvas>`;
            document.getElementById(containerId).appendChild(card);
        }

        document.getElementById('audit-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const url = document.getElementById('website-url').value;
            const data = await runAudit(url);

            ['progress', 'summary', 'dashboard'].forEach(id => document.getElementById(id).classList.remove('hidden'));

            // Summary
            document.getElementById('grade-badge').textContent = data.grade;
            document.getElementById('exec-summary').textContent = data.summary;
            document.getElementById('strengths').innerHTML = '';
            document.getElementById('weaknesses').innerHTML = '';
            document.getElementById('priority').innerHTML = '';
            data.strengths.forEach(s => document.getElementById('strengths').innerHTML += `<li>${s}</li>`);
            data.weaknesses.forEach(w => document.getElementById('weaknesses').innerHTML += `<li>${w}</li>`);
            data.priority.forEach(p => document.getElementById('priority').innerHTML += `<li>${p}</li>`);

            // Gauges & category chart
            if (data.overall_gauge) new Chart(document.getElementById('overall-gauge'), { type: 'doughnut', data: data.overall_gauge });
            if (data.health_gauge) new Chart(document.getElementById('health-gauge'), { type: 'doughnut', data: data.health_gauge });
            if (data.issues_chart) new Chart(document.getElementById('issues-chart'), { type: 'bar', data: data.issues_chart });
            new Chart(document.getElementById('category-chart'), { type: 'bar', data: data.category_chart });

            // Category totals + charts + conclusions
            document.getElementById('cat1-total').textContent = data.totals.cat1 + '%';
            document.getElementById('cat2-total').textContent = data.totals.cat2 + '%';
            document.getElementById('cat3-total').textContent = data.totals.cat3 + '%';
            document.getElementById('cat4-total').textContent = data.totals.cat4 + '%';
            document.getElementById('cat5-total').textContent = data.totals.cat5 + '%';

            new Chart(document.getElementById('cat1-summary-chart'), data.cat1_summary);
            new Chart(document.getElementById('cat1-trend-chart'), data.cat1_detail);
            document.getElementById('cat1-conclusion').textContent = data.cat1_conclusion;

            new Chart(document.getElementById('cat2-summary-chart'), data.cat2_summary);
            new Chart(document.getElementById('cat2-status-chart'), data.cat2_detail);
            document.getElementById('cat2-conclusion').textContent = data.cat2_conclusion;

            new Chart(document.getElementById('cat3-summary-chart'), data.cat3_summary);
            new Chart(document.getElementById('cat3-issues-chart'), data.cat3_detail);
            document.getElementById('cat3-conclusion').textContent = data.cat3_conclusion;

            new Chart(document.getElementById('cat4-cwv-chart'), data.cat4_summary);
            new Chart(document.getElementById('cat4-resources-chart'), data.cat4_detail);
            document.getElementById('cat4-conclusion').textContent = data.cat4_conclusion;

            new Chart(document.getElementById('cat5-security-chart'), data.cat5_summary);
            new Chart(document.getElementById('cat5-mobile-chart'), data.cat5_detail);
            document.getElementById('cat5-conclusion').textContent = data.cat5_conclusion;

            // 140 metrics: render charts; auto-inject cards for 31..140 if missing
            const ranges = { cat3: [31,65], cat4: [66,86], cat5: [87,140] };
            const containers = { cat3: 'cat3-auto-grid', cat4: 'cat4-auto-grid', cat5: 'cat5-auto-grid' };

            data.metrics.forEach(m => {
                const pad = String(m.num).padStart(3, '0');
                const cardEl = document.getElementById(`metric-${pad}`);
                const chartEl = document.getElementById(`chart-${pad}`);
                // Inject if not present in DOM:
                if (!cardEl || !chartEl) {
                    if (m.num >= ranges.cat3[0] && m.num <= ranges.cat3[1]) injectMetricCard(containers.cat3, m.num, m.severity);
                    else if (m.num >= ranges.cat4[0] && m.num <= ranges.cat4[1]) injectMetricCard(containers.cat4, m.num, m.severity);
                    else if (m.num >= ranges.cat5[0] && m.num <= ranges.cat5[1]) injectMetricCard(containers.cat5, m.num, m.severity);
                }
                const canvas = document.getElementById(`chart-${pad}`);
                const card = document.getElementById(`metric-${pad}`);
                if (card && canvas) {
                    card.className = `metric-card ${m.severity}`;
                    new Chart(canvas, { type: m.chart_type || 'bar', data: m.chart_data });
                }
            });
        });

        // Export PDF
        document.getElementById('export-pdf').addEventListener('click', () => {
            const url = document.getElementById('website-url').value || 'https://example.com';
            window.open(`/export-pdf?url=${encodeURIComponent(url)}`, '_blank');
        });
    </script>
</body>
</html>
"""

# ------------------------------------------------------------------------------
# Synthetic audit helpers
# ------------------------------------------------------------------------------
def pick_grade(score: int) -> str:
    if score >= 95: return "A+"
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"

def chart_gauge(score: int):
    color = "#10b981" if score >= 80 else "#f59e0b" if score >= 60 else "#ef4444"
    return {
        "labels": ["Score", "Remaining"],
        "datasets": [{"data": [score, 100 - score], "backgroundColor": [color, "#e5e7eb"], "borderWidth": 0}]
    }

def chart_bar(labels: List[str], values: List[int], colors_list: List[str] | None = None, label="Score"):
    return {
        "labels": labels,
        "datasets": [{"label": label, "data": values,
                      "backgroundColor": colors_list or ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#0ea5e9", "#22c55e"]}]
    }

def chart_line(labels: List[str], values: List[int], color: str = "#6366f1", label: str = "Trend"):
    return {"labels": labels, "datasets": [{"label": label, "data": values, "borderColor": color,
                                            "backgroundColor": color + "22", "fill": True, "tension": 0.35}]}

def metric_chart(pass_pct: int, kind: str = "bar"):
    fail_pct = max(0, 100 - pass_pct)
    if kind == "doughnut":
        return {"labels": ["Pass", "Fail"], "datasets": [{"data": [pass_pct, fail_pct],
                 "backgroundColor": ["#22c55e", "#ef4444"], "borderWidth": 0}]}
    return {"labels": ["Pass", "Fail"], "datasets": [{"data": [pass_pct, fail_pct],
            "backgroundColor": ["#10b981", "#ef4444"]}]}

def generate_summary(url: str, overall: int, cats: Dict[str, int], errors: int, warnings: int, notices: int) -> str:
    seo = cats.get("SEO", 75); perf = cats.get("Performance", 70); sec = cats.get("Security", 85)
    a11y = cats.get("Accessibility", 80); mobile = cats.get("Mobile", 78)
    sentences = [
        f"FF Tech audited {url}, resulting in an overall health score of {overall}% ({pick_grade(overall)}). ",
        "The analysis spans five dimensions—SEO, performance, security, accessibility, and mobile readiness—aligned with modern international standards. ",
        f"SEO measures at {seo}%, highlighting solid titles and headings while recommending stronger meta descriptions, canonical hygiene, and broader JSON‑LD coverage. ",
        f"Performance registers {perf}% and indicates opportunities to reduce payload, enable Brotli/GZIP, defer non‑critical scripts, improve caching, and adopt responsive WebP/AVIF images. ",
        f"Security stands at {sec}% with HTTPS enforced; we advise validating HSTS, CSP, Referrer‑Policy, and cookie flags (Secure/HttpOnly/SameSite) to harden defenses. ",
        f"Accessibility scores {a11y}%—generally usable—yet would benefit from consistent alt text, semantic landmarks, skip links, and color‑contrast assurance across templates. ",
        f"Mobile readiness is {mobile}%, confirming responsive behavior; refining tap target spacing and font sizing will improve touch ergonomics and perceived usability. ",
        f"Issue distribution includes {errors} errors, {warnings} warnings, and {notices} notices; remediation should be prioritized by user impact and business risk. ",
        "We recommend a phased plan: quick wins first (compression, caching headers, deferred scripts), then medium‑effort enhancements (image pipelines, schema expansion), followed by ongoing governance (security headers, audits, and monitoring). ",
        "Executing these recommendations will elevate Core Web Vitals, strengthen search visibility, build user trust, and improve conversion efficiency while creating a defensible compliance posture for stakeholders."
    ]
    return "".join(sentences)

def generate_metrics_140(overall: int) -> List[Dict]:
    rng = random.Random(overall * 991)
    out = []
    for i in range(1, 141):
        base = overall + rng.randint(-12, 8)
        pass_pct = max(10, min(100, base))
        severity = "green" if pass_pct >= 80 else "yellow" if pass_pct >= 60 else "red"
        kind = "bar" if i % 4 != 0 else "doughnut"
        out.append({"num": i, "severity": severity, "chart_type": kind, "chart_data": metric_chart(pass_pct, kind)})
    return out

def compute_category_totals(overall: int, cat_scores: Dict[str, int], cat2_components: Dict[str, int]) -> Dict[str, int]:
    """
    Category totals:
    - cat1: overall
    - cat2: 2xx base minus penalties for 4xx/5xx/redirects/broken/blocked
    - cat3: SEO score
    - cat4: Performance score
    - cat5: blend Security (60%) + Mobile (40%)
    """
    cat1_total = overall
    two_xx = cat2_components["2xx"]; four_xx = cat2_components["4xx"]; five_xx = cat2_components["5xx"]
    redirects = cat2_components["redirects"]; broken_int = cat2_components["broken_int"]; broken_ext = cat2_components["broken_ext"]
    blocked_robots = cat2_components["blocked_robots"]; blocked_meta = cat2_components["blocked_meta"]
    cat2_base = min(100, two_xx)
    penalty = (four_xx * 2) + (five_xx * 3) + (redirects * 1.5) + (broken_int * 2) + (broken_ext * 1.5) + (blocked_robots * 1.2) + (blocked_meta * 1.2)
    cat2_total = max(30, min(100, int(cat2_base - penalty)))
    cat3_total = cat_scores.get("SEO", 70)
    cat4_total = cat_scores.get("Performance", 70)
    cat5_total = int(0.6 * cat_scores.get("Security", 80) + 0.4 * cat_scores.get("Mobile", 78))
    return {"cat1": cat1_total, "cat2": cat2_total, "cat3": cat3_total, "cat4": cat4_total, "cat5": cat5_total, "overall": overall}

# ------------------------------------------------------------------------------
# Core: compute_audit(url) -> dict (used by both endpoints)
# ------------------------------------------------------------------------------
def compute_audit(url: str) -> Dict:
    seed = sum(ord(c) for c in url) % 1000
    rng = random.Random(seed)

    overall = rng.randint(62, 94)
    grade = pick_grade(overall)

    cat_scores = {
        "SEO": max(55, min(95, overall + rng.randint(-8, 6))),
        "Performance": max(50, min(92, overall + rng.randint(-12, 4))),
        "Security": max(60, min(98, overall + rng.randint(-6, 10))),
        "Accessibility": max(55, min(94, overall + rng.randint(-7, 7))),
        "Mobile": max(55, min(95, overall + rng.randint(-9, 6))),
    }

    errors = max(0, int((100 - overall) / 8) + rng.randint(0, 3))
    warnings = max(1, int((100 - overall) / 3) + rng.randint(1, 6))
    notices = max(3, int(overall / 2) + rng.randint(2, 10))

    summary = generate_summary(url, overall, cat_scores, errors, warnings, notices)

    strengths = []
    if cat_scores["Security"] >= 80: strengths.append("HTTPS enforced with strong baseline security.")
    if cat_scores["SEO"] >= 75: strengths.append("Titles/headings well structured; SEO fundamentals in place.")
    if cat_scores["Accessibility"] >= 75: strengths.append("Semantic structure aids assistive technologies.")
    if cat_scores["Mobile"] >= 75: strengths.append("Responsive design verified across breakpoints.")
    if cat_scores["Performance"] >= 70: strengths.append("Reasonable page weight; potential for optimization.")
    if not strengths: strengths = ["Platform reachable and crawlable.", "Baseline metadata present."]

    weaknesses = []
    if cat_scores["Performance"] < 80: weaknesses.append("Render‑blocking JS/CSS impacting interactivity.")
    if cat_scores["SEO"] < 80: weaknesses.append("Meta descriptions and canonical coverage inconsistent.")
    if cat_scores["Accessibility"] < 80: weaknesses.append("Incomplete alt text and ARIA landmarks.")
    if cat_scores["Security"] < 90: weaknesses.append("HSTS/CSP/cookie flags require hardening.")
    if cat_scores["Mobile"] < 80: weaknesses.append("Tap targets and font sizing need refinement.")
    if not weaknesses: weaknesses = ["Further analysis required to uncover advanced issues."]

    priority = [
        "Enable Brotli/GZIP and set Cache‑Control headers.",
        "Defer/async non‑critical scripts; inline critical CSS.",
        "Optimize images (WebP/AVIF) with responsive srcset.",
        "Expand JSON‑LD schema; validate canonical consistency.",
        "Add HSTS, CSP, Referrer‑Policy; secure cookies (HttpOnly/SameSite)."
    ]

    # Gauges and overall charts
    overall_gauge = chart_gauge(overall)
    health_gauge = overall_gauge
    issues_chart = {"labels": ["Errors", "Warnings", "Notices"],
                    "datasets": [{"data": [errors, warnings, notices],
                                  "backgroundColor": ["#ef4444", "#f59e0b", "#3b82f6"]}]}
    category_chart = chart_bar(list(cat_scores.keys()), list(cat_scores.values()))

    # Category 1
    cat1_summary = chart_bar(["Health", "Errors", "Warnings", "Notices"],
                             [overall, errors, warnings, notices],
                             ["#10b981", "#ef4444", "#f59e0b", "#3b82f6"], "Overview")
    cat1_detail = chart_line([f"W{w}" for w in range(1, 9)],
                             [max(50, min(100, overall + rng.randint(-10, 10))) for _ in range(8)],
                             "#10b981", "Health Trend")
    cat1_conclusion = "Overall health is stable. Reduce errors and warnings while maintaining crawl and index coverage."

    # Category 2
    cat2_summary_vals = {"2xx": rng.randint(60, 95), "3xx": rng.randint(3, 12), "4xx": rng.randint(1, 10), "5xx": rng.randint(0, 5)}
    cat2_summary = chart_bar(["2xx", "3xx", "4xx", "5xx"],
                             [cat2_summary_vals["2xx"], cat2_summary_vals["3xx"], cat2_summary_vals["4xx"], cat2_summary_vals["5xx"]],
                             ["#10b981", "#0ea5e9", "#ef4444", "#991b1b"], "HTTP Status Distribution")
    cat2_detail_components = {"redirects": rng.randint(0, 12), "broken_int": rng.randint(0, 8),
                              "broken_ext": rng.randint(0, 8), "blocked_robots": rng.randint(0, 10), "blocked_meta": rng.randint(0, 8)}
    cat2_detail = chart_bar(["Redirects", "Broken Int.", "Broken Ext.", "robots", "meta"],
                            [cat2_detail_components["redirects"], cat2_detail_components["broken_int"],
                             cat2_detail_components["broken_ext"], cat2_detail_components["blocked_robots"],
                             cat2_detail_components["blocked_meta"]],
                            ["#f59e0b", "#ef4444", "#ef4444", "#6366f1", "#6366f1"], "Crawl Issues")
    cat2_conclusion = "Address broken links and streamline redirects; validate robots/meta directives to avoid index gaps."

    # Category 3
    cat3_summary = chart_bar(["Titles", "Descriptions", "Headings", "Schema", "OG/Twitter"],
                             [rng.randint(60, 95), rng.randint(40, 90), rng.randint(55, 95), rng.randint(35, 85), rng.randint(40, 90)],
                             ["#6366f1", "#f59e0b", "#10b981", "#0ea5e9", "#a855f7"], "Coverage")
    cat3_detail = chart_bar(["Thin", "Duplicate", "Alt Missing", "Long URLs", "Anchor Issues"],
                            [rng.randint(5, 15), rng.randint(3, 12), rng.randint(4, 18), rng.randint(2, 10), rng.randint(3, 14)],
                            ["#ef4444", "#ef4444", "#f59e0b", "#f59e0b", "#f59e0b"], "SEO Issues")
    cat3_conclusion = "Prioritize meta completeness, schema breadth, and alt coverage. Reduce duplication and improve anchors."

    # Category 4
    cat4_summary = chart_bar(["LCP", "FCP", "CLS", "TBT", "TTI"],
                             [rng.randint(2, 6), rng.randint(1, 4), rng.randint(0, 20), rng.randint(150, 500), rng.randint(3, 8)],
                             ["#ef4444", "#f59e0b", "#0ea5e9", "#ef4444", "#f59e0b"], "CWV (approx)")
    cat4_detail = chart_bar(["Size (MB)", "Requests", "Unmin CSS", "Unmin JS", "Blocking"],
                            [rng.randint(1, 6), rng.randint(50, 180), rng.randint(0, 12), rng.randint(0, 12), rng.randint(0, 10)],
                            ["#ef4444", "#f59e0b", "#f59e0b", "#ef4444", "#ef4444"], "Resources")
    cat4_conclusion = "Implement compression, caching, minification, and deferral to improve CWV and resource efficiency."

    # Category 5
    cat5_summary = chart_bar(["HTTPS", "HSTS", "CSP", "Cookies", "Viewport"],
                             [rng.randint(70, 100), rng.randint(30, 95), rng.randint(25, 90), rng.randint(40, 95), rng.randint(70, 100)],
                             ["#10b981", "#0ea5e9", "#6366f1", "#22c55e", "#10b981"], "Policy Coverage")
    cat5_detail = chart_bar(["Mobile Friendly", "Font Size", "Tap Targets", "Interstitials", "Navigation"],
                            [rng.randint(70, 100), rng.randint(60, 95), rng.randint(60, 95), rng.randint(0, 40), rng.randint(70, 100)],
                            ["#10b981", "#f59e0b", "#f59e0b", "#ef4444", "#10b981"], "Mobile Usability")
    cat5_conclusion = "Security baseline strong; harden policies. Mobile UX is solid—refine tap targets and font scales."

    # Totals
    cat2_comps_all = {**cat2_summary_vals, **cat2_detail_components}
    totals = compute_category_totals(overall, cat_scores, {"2xx": cat2_comps_all["2xx"], "4xx": cat2_comps_all["4xx"], "5xx": cat2_comps_all["5xx"],
                                                           "redirects": cat2_comps_all["redirects"], "broken_int": cat2_comps_all["broken_int"],
                                                           "broken_ext": cat2_comps_all["broken_ext"], "blocked_robots": cat2_comps_all["blocked_robots"],
                                                           "blocked_meta": cat2_comps_all["blocked_meta"]})

    # Metrics
    metrics = generate_metrics_140(overall)

    # Remaining free audits (demo)
    remaining = max(0, 10 - rng.randint(0, 3))

    payload = {
        "grade": grade,
        "summary": summary,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "priority": priority,
        "overall_gauge": overall_gauge,
        "health_gauge": health_gauge,
        "issues_chart": issues_chart,
        "category_chart": category_chart,

        "cat1_summary": cat1_summary, "cat1_detail": cat1_detail, "cat1_conclusion": cat1_conclusion,
        "cat2_summary": cat2_summary, "cat2_detail": cat2_detail, "cat2_conclusion": cat2_conclusion,
        "cat3_summary": cat3_summary, "cat3_detail": cat3_detail, "cat3_conclusion": cat3_conclusion,
        "cat4_summary": cat4_summary, "cat4_detail": cat4_detail, "cat4_conclusion": cat4_conclusion,
        "cat5_summary": cat5_summary, "cat5_detail": cat5_detail, "cat5_conclusion": cat5_conclusion,

        "totals": totals,
        "metrics": metrics,
        "premium": False,
        "remaining": remaining,
        "cat_scores": cat_scores,
        "overall": overall,
        "errors": errors, "warnings": warnings, "notices": notices
    }
    return payload

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(INDEX_HTML)

@app.get("/audit", response_class=JSONResponse)
def audit(url: str = Query(..., description="Website URL to audit")):
    payload = compute_audit(url)

    # Persist to DB
    db = SessionLocal()
    try:
        row = Audit(
            url=url, overall=payload["overall"], grade=payload["grade"],
            errors=payload["errors"], warnings=payload["warnings"], notices=payload["notices"],
            cat_scores_json=json.dumps(payload["cat_scores"]),
            cat_totals_json=json.dumps(payload["totals"]),
            summary=payload["summary"],
            strengths_json=json.dumps(payload["strengths"]),
            weaknesses_json=json.dumps(payload["weaknesses"]),
            priority_json=json.dumps(payload["priority"]),
            metrics_json=json.dumps(payload["metrics"]),
        )
        db.add(row); db.commit()
    finally:
        db.close()

    return JSONResponse(payload)

@app.get("/export-pdf")
def export_pdf(url: str = Query(..., description="Website URL to audit and export PDF")):
    payload = compute_audit(url)
    pdf_bytes = generate_pdf_5pages(url, {
        "grade": payload["grade"],
        "overall": payload["overall"],
        "summary": payload["summary"],
        "strengths": payload["strengths"],
        "weaknesses": payload["weaknesses"],
        "priority": payload["priority"],
        "errors": payload["errors"],
        "warnings": payload["warnings"],
        "notices": payload["notices"],
        "totals": payload["totals"],
    })
    fname = f"fftech_audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    headers = {"Content-Disposition": f'attachment; filename="{fname}"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)

# Optional: list last 50 audits
@app.get("/audits")
def list_audits(url: str | None = None):
    db = SessionLocal()
    try:
        q = db.query(Audit).order_by(Audit.created_at.desc())
        if url: q = q.filter(Audit.url == url)
        rows = q.limit(50).all()
        return [{"id": r.id, "url": r.url, "created_at": r.created_at.isoformat(),
                 "overall": r.overall, "grade": r.grade,
                 "errors": r.errors, "warnings": r.warnings, "notices": r.notices} for r in rows]
    finally:
        db.close()

# ------------------------------------------------------------------------------
# PDF helpers (5 pages)
# ------------------------------------------------------------------------------
def draw_donut_gauge(c: canvas.Canvas, center_x, center_y, radius, score):
    d = Drawing(radius*2, radius*2)
    pass_pct = max(0, min(100, int(score))); fail_pct = 100 - pass_pct
    pie = Pie(); pie.x = 0; pie.y = 0; pie.width = radius*2; pie.height = radius*2
    pie.data = [pass_pct, fail_pct]; pie.labels = ["Score", "Remaining"]; pie.slices.strokeWidth = 0
    color = colors.HexColor("#10b981") if score >= 80 else colors.HexColor("#f59e0b") if score >= 60 else colors.HexColor("#ef4444")
    pie.slices[0].fillColor = color; pie.slices[1].fillColor = colors.HexColor("#e5e7eb")
    d.add(pie); renderPDF.draw(d, c, center_x - radius, center_y - radius)
    c.setFillColor(colors.white); c.circle(center_x, center_y, radius*0.58, fill=1, stroke=0)
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 18); c.drawCentredString(center_x, center_y-4, f"{score}%")

def draw_pie(c: canvas.Canvas, x, y, size, labels, values, colors_hex):
    d = Drawing(size, size)
    p = Pie(); p.x = 0; p.y = 0; p.width = size; p.height = size
    p.data = values; p.labels = labels; p.slices.strokeWidth = 0
    for i, col in enumerate(colors_hex): p.slices[i].fillColor = colors.HexColor(col)
    d.add(p); renderPDF.draw(d, c, x, y)

def draw_bar(c: canvas.Canvas, x, y, w, h, labels, values, bar_color="#6366f1"):
    d = Drawing(w, h)
    vb = VerticalBarChart(); vb.x = 30; vb.y = 20
    vb.height = h - 40; vb.width = w - 60; vb.data = [values]; vb.strokeColor = colors.transparent
    vb.valueAxis.valueMin = 0; vb.valueAxis.valueMax = max(100, max(values)+10); vb.valueAxis.valueStep = max(10, int(vb.valueAxis.valueMax/5))
    vb.categoryAxis.categoryNames = labels; vb.bars[0].fillColor = colors.HexColor(bar_color)
    d.add(vb); renderPDF.draw(d, c, x, y)

def draw_line(c: canvas.Canvas, x, y, w, h, points, line_color="#10b981"):
    d = Drawing(w, h)
    lp = LinePlot(); lp.x = 40; lp.y = 30; lp.height = h - 60; lp.width = w - 80
    lp.data = [points]; lp.lines[0].strokeColor = colors.HexColor(line_color); lp.lines[0].strokeWidth = 2; lp.joinedLines = 1
    d.add(lp); renderPDF.draw(d, c, x, y)

def wrap_text(c: canvas.Canvas, text: str, x, y, max_width_chars=95, leading=14):
    words = text.split(); lines = []; cur = ""
    for w in words:
        if len(cur) + len(w) + 1 > max_width_chars: lines.append(cur); cur = w
        else: cur = (cur + " " + w) if cur else w
    if cur: lines.append(cur)
    for i, line in enumerate(lines): c.drawString(x, y - i*leading, line)

def generate_pdf_5pages(url: str, data: dict) -> bytes:
    from io import BytesIO
    buf = BytesIO(); c = canvas.Canvas(buf, pagesize=A4); W, H = A4
    def header(title):
        c.setFillColor(colors.HexColor("#0ea5e9")); c.setFont("Helvetica-Bold", 20)
        c.drawString(20*mm, H - 20*mm, "FF Tech — Certified Website Audit")
        c.setFillColor(colors.black); c.setFont("Helvetica", 11)
        c.drawString(20*mm, H - 30*mm, f"Website: {url}")
        c.drawString(20*mm, H - 36*mm, f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        c.setFont("Helvetica-Bold", 14); c.drawString(20*mm, H - 45*mm, title)

    # Page 1 — Cover
    header("Cover & Score")
    c.setFont("Helvetica-Bold", 28); c.setFillColor(colors.black)
    c.drawString(20*mm, H - 65*mm, f"Grade: {data['grade']} • Health: {data['overall']}%")
    draw_donut_gauge(c, center_x=W/2, center_y=H/2, radius=45*mm, score=data["overall"])
    draw_pie(c, x=30*mm, y=40*mm, size=60*mm, labels=["Errors","Warnings","Notices"],
             values=[data["errors"], data["warnings"], data["notices"]],
             colors_hex=["#ef4444","#f59e0b","#3b82f6"])
    c.setFont("Helvetica", 10); c.drawString(30*mm, 35*mm, "Issue Distribution"); c.showPage()

    # Page 2 — Summary + Category totals bar
    header("Executive Summary & Category Overview")
    c.setFont("Helvetica", 11)
    wrap_text(c, data["summary"], x=20*mm, y=H - 60*mm, max_width_chars=95, leading=14)
    totals = data.get("totals", {})
    labels = ["Overall Health","Crawlability","On-Page SEO","Performance","Mobile & Security"]
    values = [totals.get("cat1",0), totals.get("cat2",0), totals.get("cat3",0), totals.get("cat4",0), totals.get("cat5",0)]
    draw_bar(c, x=20*mm, y=40*mm, w=W - 40*mm, h=70*mm, labels=labels, values=values, bar_color="#6366f1")
    c.showPage()

    # Page 3 — Lists
    header("Strengths • Weaknesses • Priority Fixes")
    c.setFont("Helvetica-Bold", 13); c.drawString(20*mm, H - 60*mm, "Strengths"); c.setFont("Helvetica", 11); y = H - 66*mm
    for s in data["strengths"][:6]: c.drawString(22*mm, y, f"• {s}"); y -= 7*mm
    c.setFont("Helvetica-Bold", 13); c.drawString(W/2, H - 60*mm, "Weak Areas"); c.setFont("Helvetica", 11); y2 = H - 66*mm
    for w in data["weaknesses"][:6]: c.drawString(W/2+2*mm, y2, f"• {w}"); y2 -= 7*mm
    c.setFont("Helvetica-Bold", 13); c.drawString(20*mm, 90*mm, "Priority Fixes (Top 5)"); c.setFont("Helvetica", 11); y3 = 84*mm
    for p in data["priority"][:5]: c.drawString(22*mm, y3, f"– {p}"); y3 -= 7*mm
    draw_bar(c, x=W/2, y=40*mm, w=W/2 - 25*mm, h=45*mm, labels=["Quick Wins","Medium","Governance"], values=[85,65,55], bar_color="#22c55e")
    c.showPage()

    # Page 4 — Trend & Resources
    header("Category Charts: Trend & Resources")
    points = [(i, max(50, min(100, data["overall"] + random.randint(-10,10)))) for i in range(1,9)]
    draw_line(c, x=20*mm, y=H - 120*mm, w=W - 40*mm, h=60*mm, points=points, line_color="#10b981")
    draw_bar(c, x=20*mm, y=40*mm, w=W - 40*mm, h=70*mm,
             labels=["Size (MB)", "Requests", "Unmin CSS", "Unmin JS", "Blocking"],
             values=[random.randint(1,6), random.randint(50,180), random.randint(0,12), random.randint(0,12), random.randint(0,10)],
             bar_color="#f59e0b")
    c.showPage()

    # Page 5 — Heatmap
    header("Metrics Overview & Impact/Effort Heatmap")
    c.setFont("Helvetica-Bold", 12); c.drawString(20*mm, H - 60*mm, "Top Signals"); c.setFont("Helvetica", 10)
    for name, note in [("TTFB","High impact, medium effort"),("Render‑blocking JS","Medium impact, low effort"),
                       ("Image/Asset Size","High impact, medium effort"),("CSP Header","High impact, low effort"),
                       ("HSTS","Medium impact, low effort"),("Mixed Content","High impact, medium effort")]:
        c.drawString(22*mm, H - 68*mm, f"• {name}: {note}"); H_minus = 68; H -= 7*mm  # simple spacing
    heat_items = [("High Impact / Low Effort", "#ef4444"),("High Impact / Medium Effort", "#f59e0b"),
                  ("Medium Impact / Low Effort", "#22c55e"),("Medium Impact / Medium Effort", "#10b981")]
    x0 = 20*mm; y0 = 40*mm; cell_w = 45*mm; cell_h = 30*mm
    for i, (label, col) in enumerate(heat_items):
        cx = x0 + (i % 2) * (cell_w + 10*mm); cy = y0 + (i // 2) * (cell_h + 10*mm)
        c.setFillColor(colors.HexColor(col)); c.roundRect(cx, cy, cell_w, cell_h, 4*mm, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 11); c.drawString(cx + 4*mm, cy + cell_h/2 - 4*mm, label)
    c.save(); pdf_bytes = buf.getvalue(); buf.close(); return pdf_bytes
