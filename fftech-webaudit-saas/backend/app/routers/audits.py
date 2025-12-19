from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl
import requests, json

router = APIRouter()

class AuditRequest(BaseModel):
    url: HttpUrl

@router.post('/')
def run_audit(req: AuditRequest):
    # Minimal checks (full engine would include 45+ metrics)
    results = {}
    try:
        r = requests.get(req.url, timeout=15)
        results['status_code'] = r.status_code
        results['https'] = req.url.startswith('https://')
        results['content_length'] = len(r.content)
        results['has_title'] = '<title>' in r.text.lower()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Fetch failed: {e}")

    # Compute simple grade
    score = 0
    score += 30 if results['https'] else 0
    score += 30 if results['status_code'] == 200 else 0
    score += 20 if results['has_title'] else 0
    score += 20 if results['content_length'] > 1024 else 0

    grade = 'A+' if score >= 90 else 'A' if score >= 80 else 'B' if score >= 70 else 'C' if score >= 60 else 'D'
    results['score'] = score
    results['grade'] = grade
    return results
