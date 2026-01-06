
"""
Audit engine for application startup checks.

This module provides:
- A registry-based plugin system for health/audit checks.
- Support for both sync and async checks executed under Uvicorn's event loop.
- Structured results with severity, timing, and error capture.
- Optional environment variable presence validation.
- Utilities to export reports to dictionaries or JSON.

Import-safe: no code executes at import time.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Tuple, Union

# Types
CheckCallable = Callable[['AuditContext'], Union['CheckResult', Awaitable['CheckResult']]]

# Registry for checks
_CHECKS: List[Tuple[str, str, CheckCallable]] = []  # (name, severity, func)

# Default logger (app can override/attach its own)
logger = logging.getLogger("audit.engine")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


@dataclass
class CheckResult:
    name: str
    passed: bool
    severity: str = "info"  # info | warning | error | critical
    duration_ms: int = 0
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "severity": self.severity,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "details": self.details,
        }


@dataclass
class AuditReport:
    results: List[CheckResult]
    total_ms: int

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def summary(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "failed": self.failed,
            "total_ms": self.total_ms,
            "by_severity": _summarize_by_severity(self.results),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary(),
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def _summarize_by_severity(results: Iterable[CheckResult]) -> Dict[str, Dict[str, int]]:
    buckets: Dict[str, Dict[str, int]] = {}
    for r in results:
        sev = r.severity
        if sev not in buckets:
            buckets[sev] = {"passed": 0, "failed": 0}
        if r.passed:
            buckets[sev]["passed"] += 1
        else:
            buckets[sev]["failed"] += 1
    return buckets


class AuditContext:
    """
    Carries application-level context for checks.
    """

    def __init__(self, app: Any, env_required: Optional[List[str]] = None):
        self.app = app
        self.env_required = env_required or []


def register_check(name: str, severity: str = "info") -> Callable[[CheckCallable], CheckCallable]:
    """
    Decorator to register a check.
    Usage:
        @register_check("My check", severity="warning")
        def my_check(ctx: AuditContext) -> CheckResult:
            ...
    """
    valid = {"info", "warning", "error", "critical"}
    if severity not in valid:
        raise ValueError(f"severity must be one of {valid}, got {severity}")

    def decorator(func: CheckCallable) -> CheckCallable:
        _CHECKS.append((name, severity, func))
        return func

    return decorator


# ---------- Built-in checks ----------

@register_check("Python version", severity="info")
def check_python_version(ctx: AuditContext) -> CheckResult:
    start = time.perf_counter()
    try:
        ver = sys.version.split()[0]  # e.g., "3.13.11"
        passed = tuple(int(x) for x in ver.split(".")[:2]) >= (3, 9)
        details = {"version": ver}
        return CheckResult(
            name="Python version",
            passed=passed,
            severity="info" if passed else "warning",
            duration_ms=int((time.perf_counter() - start) * 1000),
            error=None if passed else "Python < 3.9 (not recommended)",
            details=details,
        )
    except Exception as e:
        return CheckResult(
            name="Python version",
            passed=False,
            severity="error",
            duration_ms=int((time.perf_counter() - start) * 1000),
            error=str(e),
            details={},
        )


@register_check("App object shape", severity="info")
def check_app_object(ctx: AuditContext) -> CheckResult:
    start = time.perf_counter()
    try:
        app = ctx.app
        has_routes = hasattr(app, "routes")
        has_middleware = hasattr(app, "user_middleware") or hasattr(app, "middleware_stack")
        details = {
            "has_routes_attr": has_routes,
            "has_middleware_attr": has_middleware,
            "type": type(app).__name__,
        }
        passed = has_routes
        return CheckResult(
            name="App object shape",
            passed=passed,
            severity="info" if passed else "error",
            duration_ms=int((time.perf_counter() - start) * 1000),
            error=None if passed else "App is missing 'routes' attribute",
            details=details,
        )
    except Exception as e:
        return CheckResult(
            name="App object shape",
            passed=False,
            severity="error",
            duration_ms=int((time.perf_counter() - start) * 1000),
            error=str(e),
            details={},
        )


@register_check("Routes present", severity="warning")
def check_routes_present(ctx: AuditContext) -> CheckResult:
    start = time.perf_counter()
    try:
        app = ctx.app
        routes = getattr(app, "routes", [])
        count = len(routes) if isinstance(routes, (list, tuple)) else 0
        passed = count > 0
        return CheckResult(
            name="Routes present",
            passed=passed,
            severity="info" if passed else "warning",
            duration_ms=int((time.perf_counter() - start) * 1000),
            error=None if passed else "No routes detected on the app",
            details={"route_count": count},
        )
    except Exception as e:
        return CheckResult(
            name="Routes present",
            passed=False,
            severity="error",
            duration_ms=int((time.perf_counter() - start) * 1000),
            error=str(e),
            details={},
        )


@register_check("Middleware present", severity="info")
def check_middleware_present(ctx: AuditContext) -> CheckResult:
    start = time.perf_counter()
    try:
        app = ctx.app
        mw = getattr(app, "user_middleware", None)
        count = len(mw) if isinstance(mw, list) else 0
        return CheckResult(
            name="Middleware present",
            passed=True,  # not strictly required to pass
            severity="info",
            duration_ms=int((time.perf_counter() - start) * 1000),
            details={"middleware_count": count},
        )
    except Exception as e:
        return CheckResult(
            name="Middleware present",
            passed=False,
            severity="error",
            duration_ms=int((time.perf_counter() - start) * 1000),
            error=str(e),
            details={},
        )


@register_check("Required environment variables", severity="error")
def check_required_env(ctx: AuditContext) -> CheckResult:
    start = time.perf_counter()
    missing: List[str] = []
    try:
        for key in ctx.env_required:
            if os.getenv(key) is None:
                missing.append(key)
        passed = len(missing) == 0
        return CheckResult(
            name="Required environment variables",
            passed=passed,
            severity="info" if passed else "error",
            duration_ms=int((time.perf_counter() - start) * 1000),
            error=None if passed else f"Missing env vars: {', '.join(missing)}",
            details={"missing": missing, "required": ctx.env_required},
        )
    except Exception as e:
        return CheckResult(
            name="Required environment variables",
            passed=False,
            severity="error",
            duration_ms=int((time.perf_counter() - start) * 1000),
            error=str(e),
            details={},
        )


# ---------- Runner ----------

async def _run_check_async(name: str, severity: str, func: CheckCallable, ctx: AuditContext) -> CheckResult:
    start = time.perf_counter()
    try:
        res = func(ctx)
        if asyncio.iscoroutine(res):
            res = await res  # Await async check
        # Ensure duration is set if check didn't set it
        if res.duration_ms == 0:
            res.duration_ms = int((time.perf_counter() - start) * 1000)
        # Normalize name and severity
        res.name = res.name or name
        res.severity = res.severity or severity
        return res
    except Exception as e:
        return CheckResult(
            name=name,
            passed=False,
            severity="error",
            duration_ms=int((time.perf_counter() - start) * 1000),
            error=str(e),
            details={},
        )


async def _run_checks(ctx: AuditContext, enabled: Optional[List[str]] = None) -> AuditReport:
    start_total = time.perf_counter()
    tasks: List[Awaitable[CheckResult]] = []
    for name, severity, func in _CHECKS:
        if enabled and name not in enabled:
            continue
        tasks.append(_run_check_async(name, severity, func, ctx))
    results = await asyncio.gather(*tasks, return_exceptions=False)
    total_ms = int((time.perf_counter() - start_total) * 1000)
    return AuditReport(results=results, total_ms=total_ms)


def run_basic_checks(app: Any, env_required: Optional[List[str]] = None, *, enabled: Optional[List[str]] = None) -> AuditReport:
    """
    Public API: run registered checks against the provided app.

    - Respects the current event loop (works under Uvicorn).
    - `env_required` supplies a list of env vars to assert presence.
    - `enabled` allows selecting a subset of checks by name.
    - ENV override: AUDIT_CHECKS="Check A,Check B" to enable only listed checks.

    Returns an AuditReport.
    """
    # Allow enabling via environment variable
    env_select = os.getenv("AUDIT_CHECKS")
    if env_select:
        enabled = [x.strip() for x in env_select.split(",") if x.strip()]

    ctx = AuditContext(app=app, env_required=env_required or [])

    try:
        loop = asyncio.get_running_loop()
        # We're already inside an event loop (e.g., Uvicorn) → run via asyncio.run_coroutine_threadsafe
        fut = asyncio.run_coroutine_threadsafe(_run_checks(ctx, enabled=enabled), loop)
        report = fut.result()
    except RuntimeError:
        # No running loop → safe to create one
        report = asyncio.run(_run_checks(ctx, enabled=enabled))

    # Log a human-friendly summary
    try:
        summary = report.summary()
        logger.info(
            "Audit summary: passed=%s failed=%s total_ms=%s by_severity=%s",
            summary["passed"],
            summary["failed"],
            summary["total_ms"],
            summary["by_severity"],
        )
    except Exception:
        # Avoid hard failures on logging
        pass

    return report


__all__ = [
    "CheckResult",
    "AuditReport",
    "AuditContext",
    "register_check",
    "run_basic_checks",
]
