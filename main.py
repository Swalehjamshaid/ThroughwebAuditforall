import io, os, hashlib, time, random, urllib3, json, asyncio
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from urllib.parse import urlparse, urljoin
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from bs4 import BeautifulSoup
from fpdf import FPDF
import uvicorn
import aiohttp
import aiofiles
from collections import defaultdict
import numpy as np
import matplotlib.pyplot as plt

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(title="FF TECH | Forensic Audit Engine v6.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Ensure directories exist
os.makedirs("reports", exist_ok=True)
os.makedirs("static", exist_ok=True)

# ... [The FORENSIC_METRICS, ForensicAuditor, and ExecutivePDF classes from your snippet] ...
# Note: Ensure you include the full ForensicAuditor and ExecutivePDF logic 
# provided in your prompt to handle the 66 metrics.

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Main dashboard interface integrated with backend logic"""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>FF TECH | Forensic Audit Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            .gradient-bg { background: linear-gradient(135deg, #1e293b 0%, #334155 100%); }
            .score-circle { transition: stroke-dashoffset 0.5s ease-out; }
            .loading-bar { animation: loading 2s infinite ease-in-out; }
            @keyframes loading { 0% { width: 0%; } 50% { width: 70%; } 100% { width: 100%; } }
        </style>
    </head>
    <body class="bg-slate-50 text-slate-900 font-sans">
        <nav class="bg-white border-b border-slate-200 px-6 py-4 flex justify-between items-center sticky top-0 z-50">
            <div class="flex items-center gap-2">
                <div class="w-8 h-8 bg-blue-600 rounded flex items-center justify-center text-white">
                    <i class="fas fa-microscope"></i>
                </div>
                <h1 class="font-bold text-xl tracking-tight">FF TECH <span class="text-blue-600 font-medium">FORENSICS</span></h1>
            </div>
            <div class="hidden md:flex gap-6 text-sm font-medium text-slate-600">
                <a href="#" class="hover:text-blue-600">Dashboard</a>
                <a href="#" class="hover:text-blue-600">Metric Guide</a>
                <a href="#" class="hover:text-blue-600">History</a>
            </div>
        </nav>

        <main class="container mx-auto max-w-6xl p-6">
            <section class="bg-white rounded-2xl shadow-sm border border-slate-200 p-8 mb-8">
                <div class="max-w-3xl mx-auto text-center">
                    <h2 class="text-3xl font-extrabold text-slate-800 mb-4">Website Forensic Analysis</h2>
                    <p class="text-slate-500 mb-8">Deep-scan 66+ parameters including performance, technical SEO, security headers, and UX compliance.</p>
                    <div class="flex gap-2">
                        <input type="url" id="urlInput" placeholder="https://example.com" class="flex-grow px-4 py-3 rounded-lg border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none">
                        <button onclick="startAudit()" id="auditBtn" class="bg-blue-600 hover:bg-blue-700 text-white font-bold px-8 py-3 rounded-lg flex items-center gap-2 transition-all">
                            <i class="fas fa-bolt"></i> Run Audit
                        </button>
                    </div>
                </div>
            </section>

            <div id="loadingUI" class="hidden">
                <div class="flex flex-col items-center py-20">
                    <div class="w-16 h-16 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin mb-4"></div>
                    <p class="text-slate-600 font-medium">Executing forensic sweep...</p>
                </div>
            </div>

            <div id="resultsUI" class="hidden animate-in fade-in duration-500">
                <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
                    <div class="bg-white p-6 rounded-2xl border border-slate-200 text-center">
                        <span class="text-sm font-bold text-slate-400 uppercase tracking-widest">Health Grade</span>
                        <div id="overallScore" class="text-5xl font-black text-blue-600 my-2">0%</div>
                        <div id="gradeLabel" class="text-xs font-bold px-2 py-1 rounded bg-blue-100 text-blue-700 inline-block">SECURE</div>
                    </div>
                    <div class="bg-white p-6 rounded-2xl border border-slate-200 md:col-span-3">
                        <h3 class="font-bold mb-4">Pillar Performance</h3>
                        <div id="pillarGrid" class="grid grid-cols-2 lg:grid-cols-5 gap-4">
                            </div>
                    </div>
                </div>

                <div class="bg-white rounded-2xl border border-slate-200 overflow-hidden">
                    <div class="px-6 py-4 border-b border-slate-200 bg-slate-50 flex justify-between items-center">
                        <h3 class="font-bold">66 Forensic Metrics Matrix</h3>
                        <button onclick="downloadPDF()" class="text-sm bg-slate-900 text-white px-4 py-2 rounded-lg hover:bg-slate-800">
                            <i class="fas fa-file-pdf mr-2"></i> Export Report
                        </button>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse">
                            <thead>
                                <tr class="text-xs font-bold text-slate-400 uppercase bg-slate-50">
                                    <th class="px-6 py-4">ID</th>
                                    <th class="px-6 py-4">Metric</th>
                                    <th class="px-6 py-4">Category</th>
                                    <th class="px-6 py-4">Score</th>
                                    <th class="px-6 py-4">Status</th>
                                </tr>
                            </thead>
                            <tbody id="metricsTableBody" class="text-sm divide-y divide-slate-100">
                                </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </main>

        <script>
            let lastAuditData = null;

            async function startAudit() {
                const url = document.getElementById('urlInput').value;
                if(!url) return alert('Target URL required');

                document.getElementById('loadingUI').classList.remove('hidden');
                document.getElementById('resultsUI').classList.add('hidden');
                
                try {
                    const response = await fetch('/api/audit', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({url})
                    });
                    lastAuditData = await response.json();
                    displayResults(lastAuditData);
                } catch (e) {
                    alert('Audit failed: ' + e.message);
                } finally {
                    document.getElementById('loadingUI').classList.add('hidden');
                }
            }

            function displayResults(data) {
                document.getElementById('resultsUI').classList.remove('hidden');
                document.getElementById('overallScore').innerText = data.overall_grade + '%';
                
                // Render Pillars
                const pillarGrid = document.getElementById('pillarGrid');
                pillarGrid.innerHTML = '';
                Object.entries(data.pillars).forEach(([name, score]) => {
                    const color = score >= 80 ? 'bg-emerald-500' : score >= 60 ? 'bg-amber-500' : 'bg-rose-500';
                    pillarGrid.innerHTML += `
                        <div class="flex flex-col gap-1">
                            <span class="text-[10px] font-bold text-slate-400 uppercase">${name}</span>
                            <div class="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                                <div class="h-full ${color}" style="width: ${score}%"></div>
                            </div>
                            <span class="text-xs font-bold">${score}%</span>
                        </div>
                    `;
                });

                // Render Table
                const tbody = document.getElementById('metricsTableBody');
                tbody.innerHTML = '';
                data.metrics.forEach(m => {
                    const scoreColor = m.score >= 80 ? 'text-emerald-600' : m.score >= 60 ? 'text-amber-600' : 'text-rose-600';
                    const statusClass = m.status === 'Pass' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700';
                    tbody.innerHTML += `
                        <tr class="hover:bg-slate-50 transition-colors">
                            <td class="px-6 py-4 font-mono text-xs text-slate-400">#${m.id}</td>
                            <td class="px-6 py-4">
                                <div class="font-bold text-slate-700">${m.name}</div>
                                <div class="text-[10px] text-slate-400">${m.description}</div>
                            </td>
                            <td class="px-6 py-4 text-xs font-medium text-slate-500">${m.category}</td>
                            <td class="px-6 py-4 font-bold ${scoreColor}">${m.score}%</td>
                            <td class="px-6 py-4"><span class="px-2 py-1 rounded text-[10px] font-bold ${statusClass}">${m.status}</span></td>
                        </tr>
                    `;
                });
            }

            async function downloadPDF() {
                if(!lastAuditData) return;
                const response = await fetch('/api/download-pdf', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({audit_data: lastAuditData})
                });
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `forensic_report_${lastAuditData.report_id}.pdf`;
                a.click();
            }
        </script>
    </body>
    </html>
    """

# ... [The /api/audit and /api/download-pdf endpoints from your snippet] ...
