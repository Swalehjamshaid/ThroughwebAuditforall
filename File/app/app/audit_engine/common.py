
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import validators

DEFAULT_TIMEOUT = 15
HEADERS = {"User-Agent": "FFTechAuditBot/1.0 (+https://fftech.example)"}

def fetch(url: str):
    resp = requests.get(url, timeout=DEFAULT_TIMEOUT, allow_redirects=True, headers=HEADERS)
    return resp

def parse_html(text: str):
    return BeautifulSoup(text, 'html.parser')

def absolute(u: str, base: str) -> str:
    try:
        return urljoin(base, u)
    except Exception:
        return u
