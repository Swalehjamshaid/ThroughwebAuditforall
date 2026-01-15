
from typing import Dict, Any, List
from .crawler import crawl_site

async def analyze(url: str, competitors: List[str] | None = None) -> Dict[str, Any]:
    pages = await crawl_site(url, max_pages=30)

    total = len(pages)
    scount = {}
    sizes = []
    missing_title = missing_meta = 0
    for p in pages:
        s = p.get('status',0)
        scount[s] = scount.get(s,0)+1
        html = p.get('html','')
        if html:
            sizes.append(len(html))
            low = html.lower()
            if '<title' not in low: missing_title += 1
            if 'meta name="description"' not in low and "meta name='description'" not in low: missing_meta += 1

    m = {
        'http_2xx': sum(scount.get(x,0) for x in (200,201,204)),
        'http_3xx': sum(scount.get(x,0) for x in (301,302,304)),
        'http_4xx': sum(scount.get(x,0) for x in (400,401,403,404,410)),
        'http_5xx': sum(scount.get(x,0) for x in (500,502,503,504)),
        'total_crawled_pages': total,
        'missing_title': missing_title,
        'missing_meta_desc': missing_meta,
        'total_page_size': int(sum(sizes)/len(sizes)) if sizes else 0,
        'requests_per_page': 30
    }

    crawlability = max(0, 100 - (m['http_4xx'] + m['http_5xx'])*5 - m['http_3xx']*1)
    onpage = max(0, 100 - (missing_title + missing_meta)*2)
    performance = max(0, 100 - min(m['total_page_size']/500000*100,100))
    msi = 80.0

    cat = {
        'executive': round(crawlability*0.25+onpage*0.35+performance*0.3+msi*0.1,2),
        'overall': round(crawlability*0.4+onpage*0.4+performance*0.2,2),
        'crawlability': round(crawlability,2),
        'onpage': round(onpage,2),
        'performance': round(performance,2),
        'mobile_security_intl': round(msi,2),
        'opportunities': 70.0
    }

    return {'metrics': m, 'category_scores': cat, 'pages': pages}
