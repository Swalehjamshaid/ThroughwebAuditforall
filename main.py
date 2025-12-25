# ------------------------------------------------------------------------------
# FINAL COMPLETE INTEGRATION: World-Class Website Audit Report Structure
# Includes: AI Executive Summary, Weighted Score, Priority Matrix,
# Competitor Comparison, Risk Badges, Roadmap, White-Label, etc.
# ------------------------------------------------------------------------------

import os
import json
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from fastapi import Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
import openai  # pip install openai
import pdfkit    # pip install pdfkit (requires wkhtmltopdf binary)

# Assume existing imports and models from your main.py
# Add these new columns to User model (run migration):
# agency_mode = Column(Boolean, default=False)
# agency_name = Column(String(255), nullable=True)
# agency_logo_url = Column(String(512), nullable=True)

# Add competitor_url to Site model
# competitor_url = Column(String(1024), nullable=True)

# --------------------- 1. AI-Generated Executive Summary ---------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # or use Grok via xAI API

async def generate_ai_executive_summary(
    site_url: str,
    overall_score: int,
    grade: str,
    scores: Dict[str, int],
    totals: Dict,
    psi: Dict,
    competitor_scores: Optional[Dict] = None
) -> str:
    issues = []
    if totals.get("mixed_content_pages", 0) > 0:
        issues.append("mixed content detected")
    if totals.get("hsts_missing", 0) > 0:
        issues.append("missing HSTS header")
    if psi.get("lcp_ms", 0) > 2500:
        lcp_sec = psi["lcp_ms"] / 1000
        issues.append(f"slow mobile LCP at {lcp_sec:.1f}s")
    if totals.get("missing_titles", 0) > 0:
        issues.append("missing title tags")
    if totals.get("thin_pages", 0) > 0:
        issues.append("thin content")

    competitor_gap = ""
    if competitor_scores:
        your_lcp = psi.get("lcp_ms", 3000) / 1000
        comp_lcp = competitor_scores.get("psi", {}).get("lcp_ms", 2000) / 1000
        if your_lcp > comp_lcp:
            gap = round(your_lcp - comp_lcp, 1)
            competitor_gap = f"Your site is {gap}s slower than your direct competitor on mobile LCP."

    prompt = f"""
Write a professional, board-ready executive summary (180-220 words) for a website audit report.
Tone: Confident, decisive, business-focused for CEOs and founders.

Website: {site_url}
Overall Score: {overall_score}/100 ({grade})
Lowest Area: {min(scores, key=scores.get).capitalize()} ({scores[min(scores, key=scores.get)]}/100)
Key Issues: {', '.join(issues) if issues else 'minor optimizations needed'}
Revenue Risk: Performance delays cause user drop-off
Trust Risk: Security header gaps reduce credibility
{competitor_gap}

Top 3 Urgent Fixes:
1. Optimize Largest Contentful Paint below 2.5s
2. Implement full security headers (HSTS, CSP)
3. Fix critical SEO issues (titles, meta, schema)

End with a positive call to action about growth potential.
Do NOT use bullet points or headings. Write in paragraph form.
    """.strip()

    if OPENAI_API_KEY:
        try:
            client = openai.AsyncClient(api_key=OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",  # or "gpt-4o" for higher quality
                messages=[
                    {"role": "system", "content": "You are an elite digital strategist writing board-level reports."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=350,
                temperature=0.6
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print("AI Summary failed:", e)

    # Fallback
    return f"""
Your website {site_url} scores {overall_score}/100 ({grade}). 
The biggest growth blocker is {min(scores, key=scores.get).lower()} performance. 
Slow mobile loading and security gaps are causing estimated revenue leakage from higher bounce rates and reduced trust. 
{competitor_gap}
Immediate action on Core Web Vitals, security headers, and SEO fundamentals will restore technical trust and unlock traffic and revenue growth.
    """.strip()

# --------------------- 2. Priority Fix Matrix & Competitor Table ---------------------

def get_priority_matrix(totals: Dict, psi: Dict) -> List[Dict]:
    matrix = []
    if psi.get("lcp_ms", 0) > 2500:
        matrix.append({"priority": "HIGH", "impact": "Revenue", "effort": "Medium", "fix": "Optimize LCP below 2.5s (images, fonts, render-blocking)"})
    if totals.get("hsts_missing", 0) > 0 or totals.get("csp_missing", 0) > 0:
        matrix.append({"priority": "HIGH", "impact": "Trust", "effort": "Low", "fix": "Add HSTS, CSP, X-Frame-Options headers"})
    if totals.get("missing_meta", 0) > 0 or totals.get("missing_titles", 0) > 0:
        matrix.append({"priority": "MED", "impact": "SEO", "effort": "Low", "fix": "Add missing meta descriptions & title tags"})
    if totals.get("thin_pages", 0) > 0:
        matrix.append({"priority": "MED", "impact": "Engagement", "effort": "Medium", "fix": "Expand thin content pages"})
    return matrix or [{"priority": "LOW", "impact": "Maintenance", "effort": "Low", "fix": "All critical issues resolved"}]

def get_competitor_table(main_psi: Dict, main_scores: Dict, comp_payload: Optional[Dict]) -> List[Dict]:
    if not comp_payload:
        return [{"metric": "Competitor Analysis", "you": "-", "competitor": "No competitor URL provided", "gap": "Add one to enable"}]
    
    comp_psi = comp_payload.get("psi", {})
    comp_scores = comp_payload.get("scores", {})
    
    your_lcp = f"{main_psi.get('lcp_ms', 0)/1000:.1f}s"
    comp_lcp = f"{comp_psi.get('lcp_ms', 0)/1000:.1f}s"
    lcp_gap = "❌ Slower" if main_psi.get("lcp_ms", 0) > comp_psi.get("lcp_ms", 0) else "✅ Faster"
    
    return [
        {"metric": "Mobile LCP", "you": your_lcp, "competitor": comp_lcp, "gap": lcp_gap},
        {"metric": "Overall Score", "you": str(main_scores["overall_score"]), "competitor": str(comp_scores.get("overall_score", "-")), "gap": "❌ Lower" if main_scores["overall_score"] < comp_scores.get("overall_score", 100) else "✅ Higher"},
        {"metric": "Security Score", "you": str(main_scores["category_scores"]["Security"]), "competitor": str(comp_scores.get("category_scores", {}).get("Security", "-")), "gap": "❌ Risk" if main_scores["category_scores"]["Security"] < 80 else "✅ Secure"},
    ]

# --------------------- 3. Updated Elite PDF/HTML Report ---------------------

@app.get("/report/{audit_id}", response_class=HTMLResponse)
async def elite_report(
    audit_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user)
):
    audit = db.get(Audit, audit_id)
    if not audit or (audit.site.owner.id != user.id and not getattr(user, "agency_mode", False)):
        raise HTTPException(404)
    
    payload = json.loads(audit.payload_json)
    main = payload["main"]
    competitor = payload.get("competitor")
    
    scores = main["scores"]
    category_scores = scores["category_scores"]
    totals = scores["totals"]
    psi = main["psi"]
    
    exec_summary = await generate_ai_executive_summary(
        audit.site.url, audit.overall_score, audit.grade, category_scores, totals, psi,
        competitor["scores"] if competitor else None
    )
    
    priority_matrix = get_priority_matrix(totals, psi)
    competitor_table = get_competitor_table(psi, scores, competitor)
    
    weak_areas = scores["weak_areas"]  # already computed
    
    # White-label logic
    brand_name = getattr(user, "agency_name", None) or APP_NAME
    logo_html = f'<img src="{user.agency_logo_url}" class="h-16 mb-6" alt="Logo">' if getattr(user, "agency_mode", False) and getattr(user, "agency_logo_url", None) else ""
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>{brand_name} - Audit Report for {audit.site.url}</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap" rel="stylesheet">
        <style>
            body {{ font-family: 'Inter', sans-serif; }}
            @media print {{
                .page {{ page-break-after: always; height: 297mm; padding: 30mm 20mm; box-sizing: border-box; }}
                body {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
            }}
            .high {{ background: #fee2e2; }}
            .med {{ background: #fef3c7; }}
            .gap-bad {{ color: #dc2626; font-weight: bold; }}
            .gap-good {{ color: #16a34a; font-weight: bold; }}
            .roadmap-box {{ background: #f0f9ff; border-left: 6px solid #0ea5e9; padding: 20px; margin: 20px 0; font-size: 18px; }}
        </style>
    </head>
    <body class="bg-white text-gray-800 leading-relaxed">
    
        <!-- Page 1: Cover -->
        <div class="page text-center">
            {logo_html}
            <h1 class="text-5xl font-black text-indigo-600">{audit.grade}</h1>
            <h2 class="text-3xl font-bold mt-8">Board-Ready Website Audit Report</h2>
            <p class="text-xl mt-4">{audit.site.url}</p>
            <p class="text-gray-500 mt-8">Generated: {datetime.utcnow().strftime('%B %d, %Y')}</p>
        </div>
        
        <!-- Page 2: Executive Summary + Weighted Score -->
        <div class="page">
            <h2 class="text-3xl font-bold border-b-4 border-indigo-600 pb-4">1. Executive Summary</h2>
            <div class="mt-8 text-lg leading-relaxed bg-gray-50 p-10 rounded-xl border-l-8 border-indigo-600">
                {exec_summary.replace('\n', '<br>')}
            </div>
            
            <h2 class="text-3xl font-bold mt-12 border-b-4 border-indigo-600 pb-4">2. Global Health Score</h2>
            <table class="w-full mt-8 text-left border-collapse">
                <thead class="bg-indigo-600 text-white"><tr><th class="p-4">Area</th><th class="p-4">Weight</th><th class="p-4">Score</th></tr></thead>
                <tbody>
                    <tr><td class="p-4 font-semibold">Security</td><td class="p-4">28%</td><td class="p-4 font-bold">{category_scores['Security']}/100</td></tr>
                    <tr class="bg-gray-50"><td class="p-4 font-semibold">Performance</td><td class="p-4">27%</td><td class="p-4 font-bold">{category_scores['Performance']}/100</td></tr>
                    <tr><td class="p-4 font-semibold">SEO</td><td class="p-4">23%</td><td class="p-4 font-bold">{category_scores['SEO']}/100</td></tr>
                    <tr class="bg-gray-50"><td class="p-4 font-semibold">UX</td><td class="p-4">12%</td><td class="p-4 font-bold">{category_scores['UX']}/100</td></tr>
                    <tr><td class="p-4 font-semibold">Content</td><td class="p-4">10%</td><td class="p-4 font-bold">{category_scores['Content']}/100</td></tr>
                    <tr class="bg-indigo-600 text-white"><td class="p-4 font-bold">Overall</td><td class="p-4 font-bold">100%</td><td class="p-4 font-bold text-2xl">{audit.overall_score}/100 ({audit.grade})</td></tr>
                </tbody>
            </table>
        </div>
        
        <!-- Page 3: Priority Matrix + Competitor -->
        <div class="page">
            <h2 class="text-3xl font-bold border-b-4 border-indigo-600 pb-4">3. Priority Fix Matrix</h2>
            <table class="w-full mt-8 text-left border-collapse">
                <thead class="bg-indigo-600 text-white"><tr><th class="p-4">Priority</th><th class="p-4">Impact</th><th class="p-4">Effort</th><th class="p-4">Recommended Fix</th></tr></thead>
                <tbody>
                    {''.join(f'<tr class="{row["priority"].lower()}"><td class="p-4 font-bold">{row["priority"]}</td><td class="p-4">{row["impact"]}</td><td class="p-4">{row["effort"]}</td><td class="p-4">{row["fix"]}</td></tr>' for row in priority_matrix)}
                </tbody>
            </table>
            
            <h2 class="text-3xl font-bold mt-12 border-b-4 border-indigo-600 pb-4">4. Competitor Comparison</h2>
            <table class="w-full mt-8 text-left border-collapse">
                <thead class="bg-indigo-600 text-white"><tr><th class="p-4">Metric</th><th class="p-4">You</th><th class="p-4">Competitor</th><th class="p-4">Gap</th></tr></thead>
                <tbody>
                    {''.join(f'<tr><td class="p-4">{row["metric"]}</td><td class="p-4">{row["you"]}</td><td class="p-4">{row["competitor"]}</td><td class="p-4 font-bold { "gap-bad" if "❌" in row["gap"] else "gap-good" }">{row["gap"]}</td></tr>' for row in competitor_table)}
                </tbody>
            </table>
        </div>
        
        <!-- Page 4: Risk Badges + Roadmap -->
        <div class="page">
            <h2 class="text-3xl font-bold border-b-4 border-indigo-600 pb-4">5. Critical Risk Areas</h2>
            <div class="mt-8 flex flex-wrap gap-4">
                {''.join(f'<span class="px-6 py-3 bg-red-100 text-red-700 rounded-full text-lg font-bold border border-red-300"><i class="fas fa-exclamation-triangle mr-2"></i>{area}</span>' for area in weak_areas) or '<p class="text-green-600 text-xl">No critical risks detected – excellent technical health!</p>'}
            </div>
            
            <h2 class="text-3xl font-bold mt-12 border-b-4 border-indigo-600 pb-4">6. 30-60-90 Day Action Roadmap</h2>
            <div class="roadmap-box"><strong>30 Days:</strong> Restore Trust & Speed<br>Fix security headers + optimize LCP → Immediate reduction in bounce rates</div>
            <div class="roadmap-box"><strong>60 Days:</strong> Drive Organic Traffic<br>Resolve SEO gaps + improve content depth → Sustained visitor growth</div>
            <div class="roadmap-box"><strong>90 Days:</strong> Maximize Conversion & Revenue<br>Enhance UX, accessibility, mobile experience → Higher engagement and sales</div>
        </div>
        
        <!-- Page 5+: Technical Deep-Dive (reuse your existing collapsible categories) -->
        <!-- Insert your existing audit_categories loop here -->
        
    </body>
    </html>
    """
