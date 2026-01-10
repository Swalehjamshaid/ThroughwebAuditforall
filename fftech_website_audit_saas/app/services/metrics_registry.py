
"""Registry of metric keys and human-readable names (1..200).
This enables consistent scoring, storage, and PDF/HTML presentation.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple

@dataclass(frozen=True)
class Metric:
    id: int
    key: str
    name: str
    category: str

# Minimal programmatic registry: you can extend with more keys as needed.
# We define keys aligning with the specification; values are used throughout.

METRICS: List[Metric] = []

# Helper to add ranges

def _add_range(start: int, items: List[Tuple[str, str]], category: str):
    for i, (key, name) in enumerate(items, start=start):
        METRICS.append(Metric(id=i, key=key, name=name, category=category))

# A. Executive Summary & Grading (1–10)
_add_range(1, [
    ('overall_health_score', 'Overall Site Health Score (%)'),
    ('site_grade', 'Website Grade (A+ to D)'),
    ('executive_summary', 'Executive Summary (200 Words)'),
    ('strengths_panel', 'Strengths Highlight Panel'),
    ('weak_areas_panel', 'Weak Areas Highlight Panel'),
    ('priority_fixes_panel', 'Priority Fixes Panel'),
    ('severity_indicators', 'Visual Severity Indicators'),
    ('category_score_breakdown', 'Category Score Breakdown'),
    ('industry_standard_presentation', 'Industry-Standard Presentation'),
    ('certified_export_ready', 'Print / Certified Export Readiness'),
], 'Executive Summary')

# B. Overall Site Health (11–20)
_add_range(11, [
    ('site_health_score', 'Site Health Score'),
    ('total_errors', 'Total Errors'),
    ('total_warnings', 'Total Warnings'),
    ('total_notices', 'Total Notices'),
    ('total_crawled_pages', 'Total Crawled Pages'),
    ('total_indexed_pages', 'Total Indexed Pages'),
    ('issues_trend', 'Issues Trend'),
    ('crawl_budget_efficiency', 'Crawl Budget Efficiency'),
    ('orphan_pages_percent', 'Orphan Pages Percentage'),
    ('audit_completion_status', 'Audit Completion Status'),
], 'Overall Health')

# (You can continue populating registry for all 200 metrics as needed.)

# Fast lookup maps
METRIC_BY_ID: Dict[int, Metric] = {m.id: m for m in METRICS}
METRIC_BY_KEY: Dict[str, Metric] = {m.key: m for m in METRICS}

