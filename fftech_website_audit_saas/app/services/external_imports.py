
"""Safe import helpers for optional modules inside the project."""
from __future__ import annotations
from typing import Any, Optional, Tuple


def import_audit_report(logger) -> Tuple[Optional[Any], Optional[Any], Optional[Any]]:
    try:
        from app.audit import report as audit_report
        rp10 = getattr(audit_report, "render_pdf_10p", None)
        rp = getattr(audit_report, "render_pdf", None)
        return audit_report, rp10, rp
    except Exception as e:
        logger.info("app.audit.report not available: %s", e)
        return None, None, None


def import_grader(logger):
    try:
        from app import grader as grader_mod
        grade_all = getattr(grader_mod, "grade_all", None)
        return grade_all
    except Exception as e:
        logger.info("app.grader not available: %s", e)
        return None
