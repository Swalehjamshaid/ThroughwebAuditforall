import io, os, hashlib, time, random, requests, urllib3, ssl, re, json
from typing import List, Dict, Tuple, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
from fpdf import FPDF
import uvicorn
import asyncio
import aiohttp
from urllib.parse import urlparse, urljoin
import xml.etree.ElementTree as ET

# Suppress SSL warnings for forensic scanning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(title="FF TECH | Real Forensic Engine v6.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ------------------- 66 METRIC MASTER MAPPING -------------------
RAW_METRICS = [
    # Performance (1-15)
    (1, "Largest Contentful Paint (LCP)", "Performance"),
    (2, "First Input Delay (FID)", "Performance"),
    (3, "Cumulative Layout Shift (CLS)", "Performance"),
    (4, "First Contentful Paint (FCP)", "Performance"),
    (5, "Time to First Byte (TTFB)", "Performance"),
    (6, "Total Blocking Time (TBT)", "Performance"),
    (7, "Speed Index", "Performance"),
    (8, "Time to Interactive (TTI)", "Performance"),
    (9, "Total Page Size", "Performance"),
    (10, "HTTP Requests Count", "Performance"),
    (11, "Image Optimization", "Performance"),
    (12, "CSS Minification", "Performance"),
    (13, "JavaScript Minification", "Performance"),
    (14, "GZIP/Brotli Compression", "Performance"),
    (15, "Browser Caching", "Performance"),
    
    # Technical SEO (16-30)
    (16, "Mobile Responsiveness", "Technical SEO"),
    (17, "Viewport Configuration", "Technical SEO"),
    (18, "Structured Data Markup", "Technical SEO"),
    (19, "Canonical Tags", "Technical SEO"),
    (20, "Robots.txt Configuration", "Technical SEO"),
    (21, "XML Sitemap", "Technical SEO"),
    (22, "URL Structure", "Technical SEO"),
    (23, "Breadcrumb Navigation", "Technical SEO"),
    (24, "Title Tag Optimization", "Technical SEO"),
    (25, "Meta Description", "Technical SEO"),
    (26, "Heading Structure (H1-H6)", "Technical SEO"),
    (27, "Internal Linking", "Technical SEO"),
    (28, "External Linking Quality", "Technical SEO"),
    (29, "Schema.org Implementation", "Technical SEO"),
    (30, "AMP Compatibility", "Technical SEO"),
    
    # On-Page SEO (31-45)
    (31, "Content Quality Score", "On-Page SEO"),
    (32, "Keyword Density Analysis", "On-Page SEO"),
    (33, "Content Readability", "On-Page SEO"),
    (34, "Content Freshness", "On-Page SEO"),
    (35, "Content Length Adequacy", "On-Page SEO"),
    (36, "Image Alt Text", "On-Page SEO"),
    (37, "Video Optimization", "On-Page SEO"),
    (38, "Content Uniqueness", "On-Page SEO"),
    (39, "LSI Keywords", "On-Page SEO"),
    (40, "Content Engagement Signals", "On-Page SEO"),
    (41, "Content Hierarchy", "On-Page SEO"),
    (42, "HTTPS Full Implementation", "Security"),
    (43, "Security Headers", "Security"),
    (44, "Cross-Site Scripting Protection", "Security"),
    (45, "SQL Injection Protection", "Security"),
    
    # Security (46-55)
    (46, "Mixed Content Detection", "Security"),
    (47, "TLS/SSL Certificate Validity", "Security"),
    (48, "Cookie Security", "Security"),
    (49, "HTTP Strict Transport Security", "Security"),
    (50, "Content Security Policy", "Security"),
    (51, "Clickjacking Protection", "Security"),
    (52, "Referrer Policy", "Security"),
    (53, "Permissions Policy", "Security"),
    (54, "X-Content-Type-Options", "Security"),
    (55, "Frame Options", "Security"),
    
    # User Experience (56-66)
    (56, "Core Web Vitals Compliance", "User Experience"),
    (57, "Mobile-First Design", "User Experience"),
    (58, "Accessibility Compliance", "User Experience"),
    (59, "Page Load Animation", "User Experience"),
    (60, "Navigation Usability", "User Experience"),
    (61, "Form Optimization", "User Experience"),
    (62, "404 Error Page", "User Experience"),
    (63, "Search Functionality", "User Experience"),
    (64, "Social Media Integration", "User Experience"),
    (65, "Multilingual Support", "User Experience"),
    (66, "Progressive Web App Features", "User Experience")
]

class ForensicAuditor:
    def __init__(self, url: str):
        self.url = url
        self.domain = urlparse(url).netloc
        self.soup = None
        self.response = None
        self.ttfb = 0
        self.html_content = ""
        self.headers = {}
        
    async def fetch_page(self):
        """Fetch page with timing and headers"""
        start_time = time.time()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.url, 
                    ssl=False, 
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                ) as response:
                    self.response = response
                    self.ttfb = (time.time() - start_time) * 1000
                    self.html_content = await response.text()
                    self.headers = dict(response.headers)
                    self.soup = BeautifulSoup(self.html_content, 'html.parser')
                    return True
        except Exception as e:
            print(f"Error fetching page: {e}")
            return False

class AuditPDF(FPDF):
    def __init__(self, url, audit_data):
        super().__init__()
        self.target_url = url
        self.audit_data = audit_data
        
    def header(self):
        self.set_fill_color(15, 23, 42)
        self.rect(0, 0, 210, 45, 'F')
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(255, 255, 255)
        self.cell(0, 15, "FF TECH ELITE | FORENSIC AUDIT", 0, 1, 'C')
        self.set_font("Helvetica", "", 10)
        self.cell(0, 5, f"COMPANY: {self.target_url}", 0, 1, 'C')
        self.cell(0, 5, f"DATE: {time.strftime('%B %d, %Y')}", 0, 1, 'C')
        self.ln(20)

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve the main audit interface"""
    # Serve inline HTML
    html_content = """
    <!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FF TECH | Real Forensic Engine v6.0</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.0.0"></script>
    <style>
        :root {
            --primary: #1e40af;
            --primary-dark: #1e3a8a;
            --secondary: #0f172a;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --dark: #111827;
            --light: #f8fafc;
            --gray: #64748b;
            --gray-light: #e2e8f0;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: var(--light);
            min-height: 100vh;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 0 20px;
        }
        
        /* Header Styles */
        .header {
            background: linear-gradient(135deg, var(--secondary) 0%, #1e293b 100%);
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            padding: 1.5rem 0;
            position: sticky;
            top: 0;
            z-index: 1000;
            backdrop-filter: blur(10px);
        }
        
        .header-content {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .logo {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .logo-icon {
            background: linear-gradient(135deg, var(--primary) 0%, #3b82f6 100%);
            width: 36px;
            height: 36px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 18px;
        }
        
        .logo-text {
            font-size: 1.5rem;
            font-weight: 800;
            background: linear-gradient(135deg, #60a5fa 0%, #93c5fd 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .version {
            font-size: 0.75rem;
            color: var(--gray);
            font-weight: 600;
        }
        
        /* Hero Section */
        .hero {
            padding: 4rem 0;
            text-align: center;
        }
        
        .hero h1 {
            font-size: 3.5rem;
            font-weight: 800;
            margin-bottom: 1rem;
            background: linear-gradient(135deg, #60a5fa 0%, #93c5fd 50%, #dbeafe 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            line-height: 1.2;
        }
        
        .hero-subtitle {
            font-size: 1.25rem;
            color: var(--gray);
            max-width: 600px;
            margin: 0 auto 3rem;
            line-height: 1.6;
        }
        
        /* Input Section */
        .input-section {
            max-width: 800px;
            margin: 0 auto;
            background: rgba(30, 41, 59, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            padding: 2.5rem;
            backdrop-filter: blur(10px);
        }
        
        .input-group {
            display: flex;
            gap: 15px;
            margin-bottom: 1.5rem;
        }
        
        .url-input {
            flex: 1;
            padding: 18px 20px;
            background: rgba(15, 23, 42, 0.8);
            border: 2px solid rgba(100, 116, 139, 0.3);
            border-radius: 12px;
            color: white;
            font-size: 1rem;
            font-family: 'Inter', sans-serif;
            transition: all 0.3s ease;
        }
        
        .url-input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
        }
        
        .url-input::placeholder {
            color: #64748b;
        }
        
        .audit-btn {
            padding: 18px 36px;
            background: linear-gradient(135deg, var(--primary) 0%, #2563eb 100%);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            white-space: nowrap;
        }
        
        .audit-btn:hover {
            background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%);
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(59, 130, 246, 0.3);
        }
        
        .audit-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        .audit-btn.loading {
            position: relative;
            color: transparent;
        }
        
        .audit-btn.loading::after {
            content: '';
            position: absolute;
            width: 20px;
            height: 20px;
            top: 50%;
            left: 50%;
            margin: -10px 0 0 -10px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .example-urls {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            justify-content: center;
            margin-top: 1.5rem;
        }
        
        .example-btn {
            padding: 10px 20px;
            background: rgba(30, 41, 59, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            color: var(--gray);
            font-size: 0.9rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        .example-btn:hover {
            background: rgba(59, 130, 246, 0.1);
            color: #60a5fa;
            border-color: rgba(59, 130, 246, 0.3);
        }
        
        /* Results Section */
        .results-section {
            padding: 4rem 0;
            display: none;
        }
        
        .results-section.active {
            display: block;
        }
        
        .results-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
        }
        
        .download-btn {
            padding: 12px 24px;
            background: linear-gradient(135deg, var(--success) 0%, #34d399 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .download-btn:hover {
            background: linear-gradient(135deg, #059669 0%, #10b981 100%);
            transform: translateY(-2px);
        }
        
        .download-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        /* Score Display */
        .score-display {
            background: linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 0.8) 100%);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            padding: 2.5rem;
            margin-bottom: 3rem;
            text-align: center;
            backdrop-filter: blur(10px);
        }
        
        .overall-score {
            font-size: 5rem;
            font-weight: 800;
            margin-bottom: 1rem;
            background: linear-gradient(135deg, #60a5fa 0%, #93c5fd 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .score-label {
            font-size: 1.25rem;
            color: var(--gray);
            margin-bottom: 1.5rem;
        }
        
        .score-grade {
            display: inline-block;
            padding: 8px 20px;
            background: linear-gradient(135deg, var(--primary) 0%, #2563eb 100%);
            border-radius: 20px;
            font-weight: 600;
            font-size: 1.1rem;
            margin-bottom: 1.5rem;
        }
        
        .score-description {
            color: #94a3b8;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
        }
        
        /* Charts Section */
        .charts-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 2rem;
            margin-bottom: 3rem;
        }
        
        @media (max-width: 1024px) {
            .charts-grid {
                grid-template-columns: 1fr;
            }
        }
        
        .chart-container {
            background: rgba(30, 41, 59, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 1.5rem;
            backdrop-filter: blur(10px);
        }
        
        .chart-title {
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .chart-icon {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, var(--primary) 0%, #3b82f6 100%);
        }
        
        /* Metrics Table */
        .metrics-section {
            background: rgba(30, 41, 59, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 2rem;
            backdrop-filter: blur(10px);
        }
        
        .metrics-header {
            font-size: 1.5rem;
            font-weight: 700;
            margin-bottom: 1.5rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .metrics-table {
            width: 100%;
            border-collapse: collapse;
        }
        
        .metrics-table th {
            text-align: left;
            padding: 1rem;
            background: rgba(15, 23, 42, 0.8);
            color: #94a3b8;
            font-weight: 600;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .metrics-table th:first-child {
            border-top-left-radius: 8px;
        }
        
        .metrics-table th:last-child {
            border-top-right-radius: 8px;
        }
        
        .metrics-table td {
            padding: 1rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        .metrics-table tr:hover {
            background: rgba(59, 130, 246, 0.05);
        }
        
        .metric-category {
            font-size: 0.85rem;
            color: #64748b;
            font-weight: 500;
        }
        
        .score-indicator {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .score-bar {
            flex: 1;
            height: 8px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            overflow: hidden;
        }
        
        .score-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 1s ease;
        }
        
        .score-text {
            min-width: 40px;
            text-align: right;
            font-weight: 600;
        }
        
        /* Category Filters */
        .category-filters {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-bottom: 1.5rem;
        }
        
        .filter-btn {
            padding: 8px 16px;
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            color: #94a3b8;
            font-size: 0.9rem;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        .filter-btn.active {
            background: linear-gradient(135deg, var(--primary) 0%, #2563eb 100%);
            color: white;
            border-color: transparent;
        }
        
        .filter-btn:hover:not(.active) {
            background: rgba(59, 130, 246, 0.1);
            color: #60a5fa;
            border-color: rgba(59, 130, 246, 0.3);
        }
        
        /* Loader */
        .loader-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(15, 23, 42, 0.95);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 2000;
            backdrop-filter: blur(10px);
        }
        
        .loader-overlay.active {
            display: flex;
        }
        
        .loader {
            width: 80px;
            height: 80px;
            border: 3px solid rgba(59, 130, 246, 0.3);
            border-top-color: var(--primary);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        .loader-text {
            position: absolute;
            color: #94a3b8;
            font-size: 1rem;
            font-weight: 500;
            margin-top: 100px;
        }
        
        /* Footer */
        .footer {
            padding: 2rem 0;
            text-align: center;
            color: var(--gray);
            font-size: 0.9rem;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            margin-top: 4rem;
        }
        
        /* Responsive Design */
        @media (max-width: 768px) {
            .hero h1 {
                font-size: 2.5rem;
            }
            
            .input-group {
                flex-direction: column;
            }
            
            .audit-btn {
                width: 100%;
            }
            
            .charts-grid {
                gap: 1rem;
            }
            
            .chart-container {
                padding: 1rem;
            }
            
            .metrics-table {
                font-size: 0.9rem;
            }
            
            .metrics-table th,
            .metrics-table td {
                padding: 0.75rem 0.5rem;
            }
        }
        
        /* Animations */
        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .fade-in {
            animation: fadeIn 0.6s ease forwards;
        }
        
        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 10px;
        }
        
        ::-webkit-scrollbar-track {
            background: rgba(15, 23, 42, 0.8);
        }
        
        ::-webkit-scrollbar-thumb {
            background: linear-gradient(135deg, var(--primary) 0%, #3b82f6 100%);
            border-radius: 5px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%);
        }
    </style>
</head>
<body>
    <!-- Header -->
    <header class="header">
        <div class="container header-content">
            <div class="logo">
                <div class="logo-icon">FF</div>
                <div>
                    <div class="logo-text">FF TECH</div>
                    <div class="version">Forensic Engine v6.0</div>
                </div>
            </div>
            <div style="color: #94a3b8; font-size: 0.9rem;">
                Real-Time 66-Point Web Audit
            </div>
        </div>
    </header>

    <!-- Main Content -->
    <main class="container">
        <!-- Hero Section -->
        <section class="hero">
            <h1>Real Forensic Web Audit</h1>
            <p class="hero-subtitle">
                Comprehensive 66-point analysis of your website's performance, security, SEO, 
                and user experience. Get actionable insights powered by advanced forensic algorithms.
            </p>
            
            <!-- Input Section -->
            <div class="input-section fade-in">
                <div class="input-group">
                    <input type="url" 
                           class="url-input" 
                           placeholder="https://example.com" 
                           id="urlInput"
                           autocomplete="off">
                    <button class="audit-btn" id="auditBtn">Start Forensic Audit</button>
                </div>
                
                <div class="example-urls">
                    <div class="example-btn" onclick="setExampleUrl('https://apple.com')">apple.com</div>
                    <div class="example-btn" onclick="setExampleUrl('https://google.com')">google.com</div>
                    <div class="example-btn" onclick="setExampleUrl('https://github.com')">github.com</div>
                    <div class="example-btn" onclick="setExampleUrl('https://stackoverflow.com')">stackoverflow.com</div>
                </div>
            </div>
        </section>

        <!-- Results Section -->
        <section class="results-section" id="resultsSection">
            <div class="results-header">
                <h2 style="font-size: 1.75rem; font-weight: 700;">Audit Results</h2>
                <button class="download-btn" id="downloadBtn" disabled>
                    <svg width="20" height="20" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clip-rule="evenodd"/>
                    </svg>
                    Download PDF Report
                </button>
            </div>

            <!-- Score Display -->
            <div class="score-display fade-in" id="scoreDisplay">
                <div class="overall-score" id="overallScore">0%</div>
                <div class="score-label">Overall Health Index</div>
                <div class="score-grade" id="scoreGrade">Analyzing...</div>
                <div class="score-description" id="scoreDescription">
                    Audit in progress. Please wait while we analyze your website...
                </div>
            </div>

            <!-- Charts Grid -->
            <div class="charts-grid fade-in">
                <div class="chart-container">
                    <div class="chart-title">
                        <div class="chart-icon">📊</div>
                        Performance Analysis
                    </div>
                    <canvas id="radarChart"></canvas>
                </div>
                
                <div class="chart-container">
                    <div class="chart-title">
                        <div class="chart-icon">🎯</div>
                        Pillar Distribution
                    </div>
                    <canvas id="barChart"></canvas>
                </div>
            </div>

            <!-- Metrics Table -->
            <div class="metrics-section fade-in">
                <div class="metrics-header">
                    <div class="chart-icon">📈</div>
                    Complete 66-Metric Analysis
                </div>
                
                <div class="category-filters" id="categoryFilters">
                    <button class="filter-btn active" data-category="all">All Metrics</button>
                    <button class="filter-btn" data-category="Performance">Performance</button>
                    <button class="filter-btn" data-category="Technical SEO">Technical SEO</button>
                    <button class="filter-btn" data-category="On-Page SEO">On-Page SEO</button>
                    <button class="filter-btn" data-category="Security">Security</button>
                    <button class="filter-btn" data-category="User Experience">User Experience</button>
                </div>
                
                <div class="table-container">
                    <table class="metrics-table" id="metricsTable">
                        <thead>
                            <tr>
                                <th width="5%">#</th>
                                <th width="50%">Metric</th>
                                <th width="25%">Category</th>
                                <th width="20%">Score</th>
                            </tr>
                        </thead>
                        <tbody id="metricsTableBody">
                            <!-- Metrics will be populated here -->
                        </tbody>
                    </table>
                </div>
            </div>
        </section>
    </main>

    <!-- Footer -->
    <footer class="footer">
        <div class="container">
            <p>© 2024 FF TECH | Real Forensic Engine v6.0. All rights reserved.</p>
            <p style="margin-top: 0.5rem; font-size: 0.8rem;">
                Powered by advanced web forensic algorithms • 66-point comprehensive analysis
            </p>
        </div>
    </footer>

    <!-- Loader -->
    <div class="loader-overlay" id="loaderOverlay">
        <div class="loader"></div>
        <div class="loader-text">Analyzing 66 forensic metrics...</div>
    </div>

    <script>
        // DOM Elements
        const urlInput = document.getElementById('urlInput');
        const auditBtn = document.getElementById('auditBtn');
        const downloadBtn = document.getElementById('downloadBtn');
        const resultsSection = document.getElementById('resultsSection');
        const scoreDisplay = document.getElementById('scoreDisplay');
        const overallScore = document.getElementById('overallScore');
        const scoreGrade = document.getElementById('scoreGrade');
        const scoreDescription = document.getElementById('scoreDescription');
        const metricsTableBody = document.getElementById('metricsTableBody');
        const categoryFilters = document.getElementById('categoryFilters');
        const loaderOverlay = document.getElementById('loaderOverlay');
        
        // Chart instances
        let radarChart = null;
        let barChart = null;
        
        // Current audit data
        let currentAuditData = null;
        
        // Example URLs
        function setExampleUrl(url) {
            urlInput.value = url;
            urlInput.focus();
        }
        
        // Initialize charts
        function initializeCharts() {
            // Destroy existing charts
            if (radarChart) radarChart.destroy();
            if (barChart) barChart.destroy();
            
            // Default empty charts
            const radarCtx = document.getElementById('radarChart').getContext('2d');
            radarChart = new Chart(radarCtx, {
                type: 'radar',
                data: {
                    labels: ['Performance', 'Technical SEO', 'On-Page SEO', 'Security', 'User Experience'],
                    datasets: [{
                        label: 'Your Website',
                        data: [50, 50, 50, 50, 50],
                        backgroundColor: 'rgba(59, 130, 246, 0.2)',
                        borderColor: 'rgb(59, 130, 246)',
                        pointBackgroundColor: 'rgb(59, 130, 246)',
                        pointBorderColor: '#fff',
                        pointHoverBackgroundColor: '#fff',
                        pointHoverBorderColor: 'rgb(59, 130, 246)'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    scales: {
                        r: {
                            angleLines: {
                                display: true,
                                color: 'rgba(255, 255, 255, 0.1)'
                            },
                            grid: {
                                color: 'rgba(255, 255, 255, 0.1)'
                            },
                            pointLabels: {
                                color: '#94a3b8',
                                font: {
                                    size: 12
                                }
                            },
                            ticks: {
                                display: false,
                                max: 100,
                                min: 0,
                                stepSize: 20
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            labels: {
                                color: '#94a3b8'
                            }
                        }
                    }
                }
            });
            
            const barCtx = document.getElementById('barChart').getContext('2d');
            barChart = new Chart(barCtx, {
                type: 'bar',
                data: {
                    labels: ['Performance', 'Technical SEO', 'On-Page SEO', 'Security', 'User Experience'],
                    datasets: [{
                        label: 'Score (%)',
                        data: [50, 50, 50, 50, 50],
                        backgroundColor: [
                            'rgba(59, 130, 246, 0.8)',
                            'rgba(16, 185, 129, 0.8)',
                            'rgba(245, 158, 11, 0.8)',
                            'rgba(239, 68, 68, 0.8)',
                            'rgba(139, 92, 246, 0.8)'
                        ],
                        borderColor: [
                            'rgb(59, 130, 246)',
                            'rgb(16, 185, 129)',
                            'rgb(245, 158, 11)',
                            'rgb(239, 68, 68)',
                            'rgb(139, 92, 246)'
                        ],
                        borderWidth: 1,
                        borderRadius: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    scales: {
                        y: {
                            beginAtZero: true,
                            max: 100,
                            grid: {
                                color: 'rgba(255, 255, 255, 0.1)'
                            },
                            ticks: {
                                color: '#94a3b8',
                                callback: function(value) {
                                    return value + '%';
                                }
                           
