
import requests
from bs4 import BeautifulSoup
import validators

DEFAULT_TIMEOUT = 15

def fetch(url: str):
    resp = requests.get(url, timeout=DEFAULT_TIMEOUT, allow_redirects=True)
    return resp

def parse_html(text: str):
    return BeautifulSoup(text, 'html.parser')

def safe_url(url: str) -> bool:
    return validators.url(url)
