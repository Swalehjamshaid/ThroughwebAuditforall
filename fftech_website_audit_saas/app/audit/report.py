
#!/usr/bin/env python3
"""
Main entrypoint (CLI) for generating graphical outputs from report data and
optionally integrating outputs from other Python modules (e.g., grader.py).

Key features:
- Robust CLI parsing and logging (console + file)
- Headless matplotlib backend for safe image generation
- Report ingestion from JSON/CSV/XLSX or discovery in a directory
- Auto and configurable graph generation (histogram, bar, line)
- Optional integration with grader.py and an extra module via dynamic import
- Zero website/framework attributes (no Flask/Django), strictly CLI

Author: Updated for Khan Roy Jamshaid (Comp_HPK)
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Headless plotting (no GUI requirements)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

APP_NAME = "project-main"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_DIR = "logs"
DEFAULT_CONFIG = "config.json"
EXIT_SUCCESS = 0
EXIT_FAILURE = 1

# ------------------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------------------

def _resolve_path(p: str | Path) -> Path:
    return Path(p).expanduser().resolve()

def ensure_working_dir(base: Optional[str] = None) -> Path:
    if base:
        wd = _resolve_path(base)
        os.makedirs(wd, exist_ok=True)
        os.chdir(wd)
        return wd
    wd = _resolve_path(Path(__file__).parent)
    os.chdir(wd)
    return wd

def setup_logging(level: str = DEFAULT_LOG_LEVEL, log_dir: str = DEFAULT_LOG_DIR) -> Tuple[logging.Logger, Path]:
    lvl = getattr(logging, level.upper(), logging.INFO)
    log_path = _resolve_path(log_dir)
    os.makedirs(log_path, exist_ok=True)

    logger = logging.getLogger(APP_NAME)
    logger.setLevel(lvl)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(lvl)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    fh = logging.FileHandler(log_path / f"{APP_NAME}.log", encoding="utf-8")
    fh.setLevel(lvl)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger, log_path

def load_config(config_path: Optional[str], logger: logging.Logger) -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    if config_path:
        path = _resolve_path(config_path)
        if path.exists() and path.suffix.lower() == ".json":
            try:
                with open(path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception as e:
                logger.error("Failed to parse config JSON: %s", e, exc_info=True)
                raise
        elif not path.exists():
            logger.warning("Config file not found at %s; proceeding with defaults.", path)
        else:
            logger.warning("Unsupported config extension '%s'. Only JSON supported.", path.suffix)

    # Environment overrides
    for k in ("LOG_LEVEL", "OUTPUT_DIR"):
        v = os.getenv(k)
        if v:
            config[k.lower()] = v
    return config

def install_signal_handlers(logger: logging.Logger) -> None:
    def _handler(signum, frame):
        logger.info("Received signal %s. Shutting down gracefully...", signum)
        sys.exit(EXIT_SUCCESS)
    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)

@dataclass
class AppContext:
    logger: logging.Logger
    workdir: Path
    config: Dict[str, Any]
    start_time: float

# ------------------------------------------------------------------------------
# Dynamic module loading
# ------------------------------------------------------------------------------

def _import_module_from_path(path: str, name_hint: str = "extra_module") -> Optional[Any]:
    """
    Dynamically import a Python module from a given file path.
    Returns the module or None on failure.
    """
    try:
        full_path = _resolve_path(path)
        if not full_path.exists():
            return None
        spec = importlib.util.spec_from_file_location(name_hint, str(full_path))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        return None
    except Exception:
        return None

# ------------------------------------------------------------------------------
# Report ingestion
# ------------------------------------------------------------------------------

def _discover_report_path(report_arg: Optional[str], output_dir: Path, logger: logging.Logger) -> Optional[Path]:
    """
    Determine the report path:
    - Use --report if provided
    - Otherwise try common names in output_dir (report.json, report.csv, report.xlsx)
    - Fall back to None (caller decides)
    """
    if report_arg:
        rp = _resolve_path(report_arg)
        if rp.exists():
            return rp
        logger.warning("--report path not found: %s", rp)

    candidates = [
        output_dir / "report.json",
        output_dir / "report.csv",
        output_dir / "report.xlsx",
        output_dir / "report.xls",
    ]
    for c in candidates:
        if c.exists():
            return c
    logger.info("No report file discovered in %s.", output_dir)
    return None

def _read_csv_dicts(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows

def _read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _read_xlsx(path: Path, logger: logging.Logger) -> List[Dict[str, Any]]:
    """
    Read XLSX/XLS into list of dicts. Prefer pandas if available, else fail clearly.
    """
    try:
        import pandas as pd
        if path.suffix.lower() == ".xlsx":
            df = pd.read_excel(path, engine="openpyxl")
        else:
            df = pd.read_excel(path, engine="xlrd")
        return df.to_dict(orient="records")  # type: ignore
    except Exception as e:
        logger.error("Failed to read Excel file: %s", e, exc_info=True)
        raise

def load_report_data(report_path: Path, logger: logging.Logger) -> List[Dict[str, Any]]:
    """
    Load report data into a list of dicts for plotting. Accept JSON/CSV/XLSX.
    If JSON is a dict with key 'rows' or 'data', use that; if list, use directly.
    """
    ext = report_path.suffix.lower()
    if ext == ".json":
        payload = _read_json(report_path)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("rows", "data", "results"):
                if key in payload and isinstance(payload[key], list):
                    return payload[key]
            # flatten dict to single-row list
            return [payload]
        raise ValueError("Unsupported JSON structure for report.")
    elif ext == ".csv":
        return _read_csv_dicts(report_path)
    elif ext in (".xlsx", ".xls"):
        return _read_xlsx(report_path, logger)
    else:
        raise ValueError(f"Unsupported report extension: {ext}")

# ------------------------------------------------------------------------------
# Graph generation
# ------------------------------------------------------------------------------

def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None

def _column_types(rows: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Infer simple column types: 'numeric' or 'categorical'.
    """
    types: Dict[str, str] = {}
    if not rows:
        return types
    keys = rows[0].keys()
    for k in keys:
        values = [r.get(k) for r in rows]
        if any(_safe_float(v) is not None for v in values):
            types[k] = "numeric"
        else:
            types[k] = "categorical"
    return types

def _ensure_graph_dir(output_dir: Path) -> Path:
    gdir = output_dir / "graphs"
    os.makedirs(gdir, exist_ok=True)
    return gdir

def plot_histograms(rows: List[Dict[str, Any]], gdir: Path, logger: logging.Logger) -> List[Path]:
    paths: List[Path] = []
    types = _column_types(rows)
    numeric_cols = [k for k, t in types.items() if t == "numeric"]
    if not numeric_cols:
        logger.info("No numeric columns found for histograms.")
        return paths

    for col in numeric_cols:
        values = [_safe_float(r.get(col)) for r in rows]
        values = [v for v in values if v is not None]
        if not values:
            continue
        plt.figure(figsize=(8, 5))
        plt.hist(values, bins=10, color="#1f77b4", alpha=0.85)
        plt.title(f"Histogram: {col}")
        plt.xlabel(col)
        plt.ylabel("Frequency")
        out = gdir / f"hist_{col}.png"
        plt.tight_layout()
        plt.savefig(out)
        plt.close()
        paths.append(out)
        logger.debug("Saved histogram: %s", out)
    return paths

def plot_bar_counts(rows: List[Dict[str, Any]], gdir: Path, logger: logging.Logger) -> List[Path]:
    paths: List[Path] = []
    types = _column_types(rows)
    cat_cols = [k for k, t in types.items() if t == "categorical"]
    if not cat_cols:
        logger.info("No categorical columns found for bar charts.")
        return paths

    for col in cat_cols:
        counts: Dict[str, int] = {}
        for r in rows:
            key = str(r.get(col))
            counts[key] = counts.get(key, 0) + 1
        # Skip if too many unique values (likely IDs)
        if len(counts) > max(50, len(rows) // 2):
            continue
        labels = list(counts.keys())
        values = list(counts.values())
        plt.figure(figsize=(10, 5))
        plt.bar(labels, values, color="#ff7f0e")
        plt.xticks(rotation=45, ha="right")
        plt.title(f"Counts by {col}")
        plt.xlabel(col)
        plt.ylabel("Count")
        out = gdir / f"bar_{col}.png"
        plt.tight_layout()
        plt.savefig(out)
        plt.close()
        paths.append(out)
        logger.debug("Saved bar chart: %s", out)
    return paths

def plot_lines(rows: List[Dict[str, Any]], gdir: Path, logger: logging.Logger) -> List[Path]:
    """
    Line charts: For each numeric column, plot index vs value.
    If 'date' or 'timestamp' exists, index by it (string order preserved).
    """
    paths: List[Path] = []
    if not rows:
        return paths

    types = _column_types(rows)
    numeric_cols = [k for k, t in types.items() if t == "numeric"]
    date_key = None
    for candidate in ("date", "timestamp", "time"):
        if candidate in rows[0]:
            date_key = candidate
            break

    index_labels = [str(r.get(date_key, i)) for i, r in enumerate(rows)]
    for col in numeric_cols:
        values = [_safe_float(r.get(col)) for r in rows]
        values = [v if v is not None else float("nan") for v in values]
        plt.figure(figsize=(9, 5))
        plt.plot(index_labels, values, marker="o", color="#2ca02c")
        plt.title(f"Line: {col} over index{' (' + date_key + ')' if date_key else ''}")
        plt.xlabel(date_key or "index")
        plt.ylabel(col)
        plt.xticks(rotation=45, ha="right")
        out = gdir / f"line_{col}.png"
        plt.tight_layout()
        plt.savefig(out)
        plt.close()
        paths.append(out)
        logger.debug("Saved line chart: %s", out)
    return paths

def generate_graphs(rows: List[Dict[str, Any]], output_dir: Path, graph_types: List[str], logger: logging.Logger) -> List[Path]:
    gdir = _ensure_graph_dir(output_dir)
    generated: List[Path] = []

    types_norm = [g.strip().lower() for g in graph_types]
    auto = ("auto" in types_norm) or (not types_norm)
    if auto or "histogram" in types_norm:
        generated += plot_histograms(rows, gdir, logger)
    if auto or "bar" in types_norm:
        generated += plot_bar_counts(rows, gdir, logger)
    if auto or "line" in types_norm:
        generated += plot_lines(rows, gdir, logger)

    if not generated:
        logger.warning("No graphs generated. Check data shape or graph types.")
    else:
        logger.info("Generated %d graphs in %s", len(generated), gdir)
    return generated

# ------------------------------------------------------------------------------
# Integration with grader.py and report.py
# ------------------------------------------------------------------------------

def run_pipeline(ctx: AppContext, args: argparse.Namespace) -> Tuple[Optional[Path], List[Dict[str, Any]]]:
    """
    Try using grader.py to produce results, then report.py to build/find the report.
    If modules/functions are absent, fall back to --report path.
    Returns (report_path, rows).
    """
    logger = ctx.logger
    output_dir = _resolve_path(args.output_dir or ctx.config.get("output_dir", "artifacts"))
    os.makedirs(output_dir, exist_ok=True)

    results: Any = None
    # Try grader.py
    try:
        from grader import grade_all  # type: ignore
        logger.info("Found grader.grade_all; grading input...")
        results = grade_all(input_path=args.input, config=ctx.config, logger=logger)
    except Exception as e:
        logger.info("grader.py not used (missing or failed): %s", e)

    # Try report.py
    report_path: Optional[Path] = None
    try:
        import report  # type: ignore
        rp = None
        if hasattr(report, "build_report"):
            logger.info("Using report.build_report to create report...")
            rp = report.build_report(results, output_dir=output_dir, logger=logger)  # type: ignore
        elif hasattr(report, "get_report_path"):
            logger.info("Using report.get_report_path to locate report...")
            rp = report.get_report_path(output_dir=output_dir, logger=logger)  # type: ignore
        if rp:
            report_path = _resolve_path(rp)
    except Exception as e:
        logger.info("report.py not used (missing or failed): %s", e)

    # If not found, discover or use --report
    if not report_path:
        report_path = _discover_report_path(args.report, output_dir, logger)

    rows: List[Dict[str, Any]] = []
    if report_path:
        try:
            rows = load_report_data(report_path, logger)
            logger.info("Loaded %d rows from report: %s", len(rows), report_path)
        except Exception as e:
            logger.error("Failed to load report data: %s", e, exc_info=True)
    else:
        logger.warning("No report path available. Graphs can still be generated from extra module data if provided.")

    # Optional extra module
    if args.extra_module:
        mod = _import_module_from_path(args.extra_module, "extra_module")
        if mod:
            try:
                if hasattr(mod, "compute_metrics"):
                    extra_rows = mod.compute_metrics(results, ctx.config)  # type: ignore
                    if isinstance(extra_rows, list):
                        rows += extra_rows
                        logger.info("Appended %d rows from extra module compute_metrics.", len(extra_rows))
                elif hasattr(mod, "get_data"):
                    extra_rows = mod.get_data()  # type: ignore
                    if isinstance(extra_rows, list):
                        rows += extra_rows
                        logger.info("Appended %d rows from extra module get_data.", len(extra_rows))
                else:
                    logger.info("Extra module has no compute_metrics/get_data; skipped.")
            except Exception as e:
                logger.error("Extra module invocation failed: %s", e, exc_info=True)
        else:
            logger.warning("Could not import extra module from path: %s", args.extra_module)

    return report_path, rows

# ------------------------------------------------------------------------------
# CLI & runners
# ------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="CLI tool to generate graphical outputs from report data (no website attributes)."
    )
    parser.add_argument("-c", "--config", default=DEFAULT_CONFIG,
                        help=f"Path to config JSON (default: {DEFAULT_CONFIG}).")
    parser.add_argument("-o", "--output-dir", default=None,
                        help="Output directory for artifacts (graphs, logs).")
    parser.add_argument("-l", "--log-level", default=DEFAULT_LOG_LEVEL,
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help=f"Logging level (default: {DEFAULT_LOG_LEVEL}).")
    parser.add_argument("-w", "--workdir", default=None,
                        help="Optional working directory to chdir into before running.")
    parser.add_argument("-i", "--input", default=None,
                        help="Input path (file or directory) used by grader.py if available.")
    parser.add_argument("-r", "--report", default=None,
                        help="Path to existing report file or directory (JSON/CSV/XLSX).")
    parser.add_argument("-g", "--graph-types", default="auto",
                        help="Comma-separated graph types: auto, histogram, bar, line (default: auto).")
    parser.add_argument("-e", "--extra-module", default=None,
                        help="Path to an extra Python file providing compute_metrics(results, config) or get_data().")
    parser.add_argument("-a", "--async", dest="use_async", action="store_true",
                        help="Run in async mode (mostly useful if integrations are async).")
    return parser

def run_sync(ctx: AppContext, args: argparse.Namespace) -> int:
    logger = ctx.logger
    logger.info("Starting synchronous run.")
    logger.debug("Arguments: %s", vars(args))
    logger.debug("Config: %s", ctx.config)

    try:
        report_path, rows = run_pipeline(ctx, args)
        output_dir = _resolve_path(args.output_dir or ctx.config.get("output_dir", "artifacts"))
        graphs = generate_graphs(rows, output_dir, args.graph_types.split(","), logger)

        if graphs:
            logger.info("Run completed. Generated graphs:")
            for g in graphs:
                logger.info(" - %s", g)
        else:
            logger.warning("Run completed with no graphs generated.")
        return EXIT_SUCCESS
    except Exception as e:
        logger.error("Unhandled exception in run_sync: %s", e, exc_info=True)
        return EXIT_FAILURE

async def run_async(ctx: AppContext, args: argparse.Namespace) -> int:
    ctx.logger.info("Starting asynchronous run.")
    # For now, just delegate to sync logic; replace with real async if needed.
    return run_sync(ctx, args)

def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    workdir = ensure_working_dir(args.workdir)
    logger, _ = setup_logging(level=args.log_level, log_dir=DEFAULT_LOG_DIR)
    install_signal_handlers(logger)

    try:
        config = load_config(args.config, logger)
    except Exception:
        return EXIT_FAILURE

    ctx = AppContext(logger=logger, workdir=workdir, config=config, start_time=time.time())

    if args.use_async:
        try:
            return asyncio.run(run_async(ctx, args))
        except RuntimeError as e:
            logger.warning("Existing event loop detected; using fallback. %s", e)
            try:
                import nest_asyncio  # optional
                nest_asyncio.apply()
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(run_async(ctx, args))
            except Exception as ee:
                logger.error("Async fallback failed: %s", ee, exc_info=True)
                return EXIT_FAILURE
    else:
        return run_sync(ctx, args)

if __name__ == "__main__":
    sys.exit(main())
