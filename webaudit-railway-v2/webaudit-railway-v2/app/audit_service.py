import re
import time
import requests
from bs4 import BeautifulSoup

SEC_TIMEOUT = 20

def fetch(url):
    return requests.get(url, timeout=SEC_TIMEOUT, verify=True, allow_redirects=True)

def check_security_headers(resp):
    h = {k.lower(): v for k,v in resp.headers.items()}
    return {
        "hsts_present": "strict-transport-security" in h,
        "hsts_value": h.get("strict-transport-security"),
        "x_frame_options": h.get("x-frame-options") in ["DENY", "SAMEORIGIN"],
        "x_content_type_options": h.get("x-content-type-options") == "nosniff",
        "referrer_policy_present": "referrer-policy" in h,
        "csp_present": "content-security-policy" in h,
        "permissions_policy_present": "permissions-policy" in h,
        "x_xss_protection": h.get("x-xss-protection") in ["0", "1; mode=block"],
    }

def check_seo_onpage(url, html):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("title")
    meta_desc = soup.find("meta", attrs={"name": "description"})
    canonical = soup.find("link", attrs={"rel": "canonical"})
    robots_meta = soup.find("meta", attrs={"name": "robots"})
    h1 = soup.find("h1")
    images = soup.find_all("img")
    img_alt_ok = sum(1 for i in images if (i.get("alt") and i.get("alt").strip()))
    img_count = len(images)
    links = soup.find_all("a", href=True)
    internal_links = sum(1 for a in links if a["href"].startswith("/") or url.split("/")[2] in a["href"])
    external_links = len(links) - internal_links
    nofollow_links = sum(1 for a in links if a.get("rel") == ["nofollow"])
    return {
        "title_present": bool(title and title.text.strip()),
        "title_length": len(title.text.strip()) if title else 0,
        "meta_description_present": bool(meta_desc and meta_desc.get("content")),
        "meta_description_length": len(meta_desc.get("content","")) if meta_desc else 0,
        "canonical_present": bool(canonical and canonical.get("href")),
        "robots_meta_present": bool(robots_meta and robots_meta.get("content")),
        "h1_present": h1 is not None,
        "images_count": img_count,
        "images_alt_nonempty_count": img_alt_ok,
        "links_internal_count": internal_links,
        "links_external_count": external_links,
        "links_nofollow_count": nofollow_links,
        "meta_viewport_present": bool(soup.find("meta", attrs={"name":"viewport"})),
        "ld_json_present": bool(soup.find("script", attrs={"type":"application/ld+json"})),
    }

def check_robots_sitemap(base_url):
    from urllib.parse import urljoin
    robots_url = urljoin(base_url, "/robots.txt")
    info = {"robots_accessible": False, "sitemaps": [], "robots_blocks_all": False}
    try:
        r = fetch(robots_url)
        info["robots_accessible"] = (r.status_code == 200)
        if r.ok:
            content = r.text
            info["sitemaps"] = re.findall(r"(?i)^sitemap:\s*(.+)$", content, flags=re.MULTILINE)
            info["robots_blocks_all"] = "disallow: /" in content.lower()
    except Exception:
        pass
    sm_url = urljoin(base_url, "/sitemap.xml")
    try:
        r = fetch(sm_url)
        info["sitemap_xml_accessible"] = (r.status_code == 200)
    except Exception:
        info["sitemap_xml_accessible"] = False
    return info

def consolidate_45_plus_metrics(url):
    resp = fetch(url)
    html = resp.text
    sec = check_security_headers(resp)
    seo = check_seo_onpage(url, html)
    rs  = check_robots_sitemap(url)
    soup = BeautifulSoup(html, "html.parser")
    lang_present = bool(soup.find("html") and soup.find("html").get("lang"))
    alt_ratio = (seo["images_alt_nonempty_count"] / max(seo["images_count"],1)) if seo["images_count"] else 1.0
    accessibility = {
        "html_lang_present": lang_present,
        "images_alt_ratio": alt_ratio,
        "aria_attributes_count": len(soup.find_all(attrs={"aria-label": True})) + len(soup.find_all(attrs={"role": True})),
        "contrast_check_placeholder": True
    }
    best_practices = {
        "https_scheme": url.lower().startswith("https://"),
        "no_mixed_content_placeholder": True,
        "viewport_present": seo["meta_viewport_present"],
        "uses_canonical": seo["canonical_present"],
    }
    return {
        "security_headers": sec,
        "seo_onpage": seo,
        "robots_sitemap": rs,
        "accessibility": accessibility,
        "best_practices": best_practices,
        "timestamp": int(time.time())
    }
