from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl
import requests

router = APIRouter()

class AuditRequest(BaseModel):
    url: HttpUrl

@router.post('/')
def run(req: AuditRequest):
    try:
        r = requests.get(req.url, timeout=15)
        return {
            'status_code': r.status_code,
            'https': req.url.startswith('https://'),
            'has_title': '<title>' in r.text.lower(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
