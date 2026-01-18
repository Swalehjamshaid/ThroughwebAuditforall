
from typing import Dict, Any
from .crawler import crawl
from .grader import Grader
from .metrics_catalog import METRICS
import asyncio

async def audit_site(url: str, max_pages: int = 30) -> Dict[str, Any]:
    data = await crawl(url, max_pages=max_pages)
    findings: Dict[int, Dict[str, Any]] = {}

    pages = data['pages']
    statuses = [p.get('status', 0) for p in pages.values()]
    errors = sum(1 for s in statuses if 400 <= s < 600)
    warnings = sum(1 for s in statuses if 300 <= s < 400)

    findings[11] = {"value": None, "score": max(0, 100 - errors*2 - warnings)}
    findings[12] = {"value": errors, "score": max(0, 100 - errors*5)}
    findings[13] = {"value": warnings, "score": max(0, 100 - warnings*2)}
    findings[15] = {"value": len(pages), "score": min(100, len(pages)*2)}

    missing_title = sum(1 for p in pages.values() if not p.get('title'))
    findings[41] = {"value": missing_title, "score": max(0, 100 - missing_title*5)}

    missing_h1 = sum(1 for p in pages.values() if len(p.get('h1s', [])) == 0)
    multi_h1 = sum(1 for p in pages.values() if len(p.get('h1s', [])) > 1)
    findings[49] = {"value": missing_h1, "score": max(0, 100 - missing_h1*5)}
    findings[50] = {"value": multi_h1, "score": max(0, 100 - multi_h1*3)}

    og_missing = sum(1 for p in pages.values() if not p.get('opengraph'))
    findings[62] = {"value": og_missing, "score": max(0, 100 - og_missing*2)}

    vp_missing = sum(1 for p in pages.values() if not p.get('viewport'))
    findings[98] = {"value": vp_missing, "score": max(0, 100 - vp_missing*5)}

    findings[168] = {"value": errors, "score": max(0, 100 - errors*2)}

    grader = Grader(findings)
    overall = grader.overall()

    findings[1] = {"value": overall['score'], "score": overall['score']}
    findings[2] = {"value": overall['grade'], "score": overall['score']}

    metrics_out: Dict[str, Any] = {}
    for mid in sorted(METRICS.keys()):
        m = grader.score_metric(mid)
        metrics_out[str(mid)] = m

    summary = f"Crawled {len(pages)} pages. Errors: {errors}, warnings: {warnings}. Overall score {overall['score']} (grade {overall['grade']})."

    return {
        'summary': summary,
        'metrics': metrics_out,
        'overall': overall,
        'pages': data['pages']
    }

def audit_site_sync(url: str, max_pages: int = 30) -> Dict[str, Any]:
    return asyncio.get_event_loop().run_until_complete(audit_site(url, max_pages))
