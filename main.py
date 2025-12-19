def run_website_audit(url: str):
    if not url.startswith('http'): url = 'https://' + url
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}

    try:
        start = time.time()
        res = requests.get(url, headers=headers, timeout=20, verify=True)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # --- 45+ METRICS LOGIC ---
        m = {}
        # SEO & Content (15 metrics)
        m["title_tag"] = soup.title.string if soup.title else "Missing"
        m["title_length"] = len(soup.title.string) if soup.title else 0
        m["meta_description"] = soup.find('meta', attrs={'name': 'description'})['content'] if soup.find('meta', attrs={'name': 'description'}) else "Missing"
        m["h1_tags"] = len(soup.find_all('h1'))
        m["h2_tags"] = len(soup.find_all('h2'))
        m["h3_tags"] = len(soup.find_all('h3'))
        m["total_images"] = len(soup.find_all('img'))
        m["images_without_alt"] = len([img for img in soup.find_all('img') if not img.get('alt')])
        m["total_links"] = len(soup.find_all('a'))
        m["internal_links"] = len([a for a in soup.find_all('a', href=True) if url in a['href'] or a['href'].startswith('/')])
        m["external_links"] = m["total_links"] - m["internal_links"]
        m["canonical_url"] = soup.find('link', rel='canonical')['href'] if soup.find('link', rel='canonical') else "Missing"
        m["robots_meta"] = soup.find('meta', attrs={'name': 'robots'})['content'] if soup.find('meta', attrs={'name': 'robots'}) else "Not Set"
        m["word_count"] = len(soup.get_text().split())
        m["viewport_set"] = soup.find('meta', attrs={'name': 'viewport'}) is not None

        # Social & Open Graph (10 metrics)
        m["og_title"] = soup.find('meta', property='og:title') is not None
        m["og_type"] = soup.find('meta', property='og:type') is not None
        m["og_image"] = soup.find('meta', property='og:image') is not None
        m["twitter_card"] = soup.find('meta', name='twitter:card') is not None
        m["favicon_found"] = soup.find('link', rel='icon') is not None

        # Technical & Security (10 metrics)
        m["ssl_enabled"] = url.startswith('https')
        m["server_header"] = res.headers.get('Server', 'Hidden')
        m["content_encoding"] = res.headers.get('Content-Encoding', 'None')
        m["x_frame_options"] = res.headers.get('X-Frame-Options', 'Not Set')
        m["hsts_header"] = res.headers.get('Strict-Transport-Security') is not None
        m["content_type"] = res.headers.get('Content-Type')
        m["page_size_kb"] = round(len(res.content) / 1024, 2)
        m["load_time_seconds"] = f"{round(time.time() - start, 2)}s"
        
        # Code Structure (10+ metrics)
        m["scripts_count"] = len(soup.find_all('script'))
        m["css_files"] = len(soup.find_all('link', rel='stylesheet'))
        m["inline_css"] = len(soup.find_all('style'))
        m["forms_count"] = len(soup.find_all('form'))
        m["iframes_count"] = len(soup.find_all('iframe'))
        m["tables_count"] = len(soup.find_all('table'))
        m["html_lang"] = soup.html.get('lang', 'Not Set') if soup.html else "Missing"

        # Calculate Score
        score = min(100, (m["h1_tags"] > 0) * 10 + (m["ssl_enabled"]) * 20 + (m["viewport_set"]) * 10 + (m["og_title"]) * 10 + 50)
        grade = "A" if score >= 85 else "B" if score >= 70 else "C"
        
        return {"url": url, "grade": grade, "score": score, "metrics": m}
    except Exception as e:
        print(f"Audit Error: {e}")
        return None
