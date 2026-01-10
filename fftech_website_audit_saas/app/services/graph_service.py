
from __future__ import annotations
from typing import Any, Dict, List
from pathlib import Path
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from .config import resolve_path


def safe_float(v: Any):
    try:
        return float(v)
    except Exception:
        return None


def column_types(rows: List[Dict[str, Any]]):
    types = {}
    if not rows:
        return types
    for k in rows[0].keys():
        values = [r.get(k) for r in rows]
        if any(safe_float(v) is not None for v in values):
            types[k] = 'numeric'
        else:
            types[k] = 'categorical'
    return types


def ensure_graph_dir(static_dir: Path) -> Path:
    gdir = resolve_path(static_dir / 'img' / 'graphs')
    os.makedirs(gdir, exist_ok=True)
    return gdir


def plot_histograms(rows: List[Dict[str, Any]], gdir: Path, logger):
    paths = []
    types = column_types(rows)
    numeric_cols = [k for k,t in types.items() if t=='numeric']
    for col in numeric_cols:
        values = [safe_float(r.get(col)) for r in rows]
        values = [v for v in values if v is not None]
        if not values:
            continue
        plt.figure(figsize=(8,5))
        plt.hist(values, bins=10, color='#1f77b4', alpha=0.85)
        plt.title(f'Histogram: {col}')
        plt.xlabel(col); plt.ylabel('Frequency')
        out = gdir / f'hist_{col}.png'
        plt.tight_layout(); plt.savefig(out); plt.close()
        logger.debug('Saved histogram: %s', out)
        paths.append(out)
    return paths


def plot_bar_counts(rows: List[Dict[str, Any]], gdir: Path, logger):
    paths = []
    types = column_types(rows)
    cat_cols = [k for k,t in types.items() if t=='categorical']
    for col in cat_cols:
        counts = {}
        for r in rows:
            key = str(r.get(col))
            counts[key] = counts.get(key, 0) + 1
        if len(counts) > max(50, len(rows)//2):
            continue
        labels = list(counts.keys()); values = list(counts.values())
        plt.figure(figsize=(10,5))
        plt.bar(labels, values, color='#ff7f0e')
        plt.xticks(rotation=45, ha='right')
        plt.title(f'Counts by {col}')
        plt.xlabel(col); plt.ylabel('Count')
        out = gdir / f'bar_{col}.png'
        plt.tight_layout(); plt.savefig(out); plt.close()
        logger.debug('Saved bar chart: %s', out)
        paths.append(out)
    return paths


def plot_lines(rows: List[Dict[str, Any]], gdir: Path, logger):
    paths = []
    if not rows:
        return paths
    types = column_types(rows)
    numeric_cols = [k for k,t in types.items() if t=='numeric']
    date_key = None
    for candidate in ('date','timestamp','time'):
        if candidate in rows[0]:
            date_key = candidate; break
    index_labels = [str(r.get(date_key, i)) for i,r in enumerate(rows)]
    for col in numeric_cols:
        values = [safe_float(r.get(col)) for r in rows]
        values = [v if v is not None else float('nan') for v in values]
        plt.figure(figsize=(9,5))
        plt.plot(index_labels, values, marker='o', color='#2ca02c')
        plt.title(f'Line: {col} over index' + (f' ({date_key})' if date_key else ''))
        plt.xlabel(date_key or 'index'); plt.ylabel(col)
        plt.xticks(rotation=45, ha='right')
        out = gdir / f'line_{col}.png'
        plt.tight_layout(); plt.savefig(out); plt.close()
        logger.debug('Saved line chart: %s', out)
        paths.append(out)
    return paths


def generate_graphs(rows: List[Dict[str, Any]], static_dir: Path, graph_types: list[str], logger):
    gdir = ensure_graph_dir(static_dir)
    generated = []
    types_norm = [g.strip().lower() for g in graph_types]
    auto = ('auto' in types_norm) or (not types_norm)
    if auto or 'histogram' in types_norm:
        generated += plot_histograms(rows, gdir, logger)
    if auto or 'bar' in types_norm:
        generated += plot_bar_counts(rows, gdir, logger)
    if auto or 'line' in types_norm:
        generated += plot_lines(rows, gdir, logger)
    return generated

