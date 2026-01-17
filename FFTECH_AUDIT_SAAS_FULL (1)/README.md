# FF Tech AI Website Audit SaaS — PRO (All Features + Automation)

- Open access audits + passwordless login
- 200-metric framework (extensible) with transparent scoring (A+..D)
- **PSI Core Web Vitals** (LCP/FCP/CLS/TBT/SpeedIndex/TTI) via API key
- **Gemini AI** executive summary & narratives
- **5-page PDF** + PPTX + XLSX + PNG exports
- **Competitor** comparison endpoint
- **Scheduler** (daily/weekly/monthly) for subscribers
- **Admin** overview endpoint (token)
- **Railway automation** scripts to push `.env` via Public GraphQL API

## Quick Start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

## Deploy to Railway
- Upload this folder or connect a GitHub repo
- Add variables from `.env` to Railway → Variables
- (Optional) Run scripts in `scripts/` to push variables automatically
