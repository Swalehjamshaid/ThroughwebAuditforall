
import requests
from ..config import settings

RESEND_API_URL = 'https://api.resend.com/emails'

class EmailError(Exception):
    pass

def send_email(to: str, subject: str, html: str):
    if not settings.RESEND_API_KEY:
        raise EmailError('RESEND_API_KEY not configured')
    headers = {
        'Authorization': f'Bearer {settings.RESEND_API_KEY}',
        'Content-Type': 'application/json'
    }
    payload = {
        'from': settings.RESEND_FROM_EMAIL,
        'to': [to],
        'subject': subject,
        'html': html
    }
    resp = requests.post(RESEND_API_URL, json=payload, headers=headers, timeout=20)
    if resp.status_code >= 300:
        raise EmailError(f'Resend API error: {resp.status_code} {resp.text}')
    return resp.json()
