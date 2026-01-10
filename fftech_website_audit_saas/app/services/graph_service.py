# app/services/graph_service.py
# -*- coding: utf-8 -*-

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pathlib import Path
import os
import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from math import pi

from .config import resolve_path

# FF Tech Brand Colors
COLORS = {
    'primary': '#4F46E5',   # Indigo
    'success': '#10B981',   # Emerald
    'warning': '#F59E0B',   # Amber
    'danger': '#EF4444',    # Rose
    'neutral': '#EEEEEE',   # Light Gray
    'text': '#333333'
}

def safe_float(v: Any):
    try:
        return float(v)
    except (TypeError, ValueError):
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

def ensure_graph_dir(static_dir: Path, run_id: str | None = None) -> Path:
    base = static_dir / 'img' / 'graphs'
    gdir = resolve_path(base / (run_id or 'common'))
    os.makedirs(gdir, exist_ok=True)
    return gdir

# -------------------------- NEW: EXECUTIVE GRAPHICS --------------------------

def plot_health_gauge(score: int, gdir: Path, logger):
    """Generates a professional Donut Gauge for Overall Health."""
    score = max(0, min(100, int(score)))
    fig, ax = plt.subplots(figsize=(4, 4))
    
    # Logic for color based on score
    color = COLORS['success'] if score >= 80 else COLORS['warning'] if score >= 50 else COLORS['danger']
    
    ax.pie([score, 100 - score], colors=[color, COLORS['neutral']], 
           startangle=90, counterclock=False, wedgeprops=dict(width=0.3, edgecolor='white'))
    
    plt.text(0, 0, f"{score}%", ha='center', va='center', fontsize=24, fontweight='bold', color=COLORS['text'])
    plt.title("Overall Site Health", fontsize=12, pad=10)
    
    out = gdir / 'health_gauge.png'
    plt.savefig(out, transparent=True, dpi=150); plt.close()
    return out



def plot_radar_chart(categories: Dict[str, int], gdir: Path, logger, competitor_cats: Optional[Dict[str, int]] = None):
    """Generates a Radar Chart (Spider Map) for Category Breakdown A-I."""
    labels = list(categories.keys())
    values = list(categories.values())
    N = len(labels)
    
    angles = [n / float(N) * 2 * pi for n in range(N)]
    angles += angles[:1]
    
    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    ax.set_theta_offset(pi / 2)
    ax.set_theta_direction(-1)

    # Main Site
    val_plot = values + values[:1]
    ax.plot(angles, val_plot, color=COLORS['primary'], linewidth=2, linestyle='solid')
    ax.fill(angles, val_plot, color=COLORS['primary'], alpha=0.25, label="Your Site")

    # Competitor Overlay (Category G)
    if competitor_cats:
        c_vals = [competitor_cats.get(l, 0) for l in labels]
        c_vals += c_vals[:1]
        ax.plot(angles, c_vals, color=COLORS['danger'], linewidth=2, linestyle='dashed')
        ax.fill(angles, c_vals, color=COLORS['danger'], alpha=0.1, label="Competitor")
        ax.legend(loc='upper right', bbox_to_anchor=(0.1, 0.1), fontsize=8)

    plt.xticks(angles[:-1], labels, color='grey', size=10)
    ax.set_rlabel_position(0)
    plt.yticks([25, 50, 75, 100], ["25", "50", "75", "100"], color="grey", size=7)
    plt.ylim(0, 100)
    
    out = gdir / 'radar_categories.png'
    plt.savefig(out, transparent=True, dpi=150); plt.close()
    return out



def plot_security_heatmap(sec_data: Dict[str, bool], gdir: Path, logger):
    """Generates a 2x3 Heatmap for Category F: Security Compliance."""
    keys = list(sec_data.keys())
    vals = [1 if sec_data[k] else 0 for k in keys]
    
    # Pad if necessary to fit grid
    while len(vals) < 6: vals.append(0); keys.append("N/A")
    
    grid = np.array(vals[:6]).reshape(2, 3)
    fig, ax = plt.subplots(figsize=(5, 3))
    cmap = mcolors.ListedColormap([COLORS['danger'], COLORS['success']])
    
    ax.imshow(grid, cmap=cmap)
    ax.set_xticks([]); ax.set_yticks([])
    
    for i in range(2):
        for j in range(3):
            idx = i * 3 + j
            status = "PASS" if vals[idx] else "FAIL"
            ax.text(j, i, f"{keys[idx]}\n{status}", ha='center', va='center', color='white', fontweight='bold', fontsize=9)

    plt.title("Security Posture Heatmap", fontsize=11)
    out = gdir / 'security_heatmap.png'
    plt.savefig(out, bbox_inches='tight', dpi=150); plt.close()
    return out



# -------------------------- PRESERVED & IMPROVED ORIGINAL LOGIC --------------------------

def plot_histograms(rows: List[Dict[str, Any]], gdir: Path, logger):
    paths = []
    types = column_types(rows)
    numeric_cols = [k for k,t in types.items() if t=='numeric']
    for col in numeric_cols:
        values = [safe_float(r.get(col)) for r in rows]
        values = [v for v in values if v is not None]
        if not values: continue
        
        plt.figure(figsize=(8,5))
        plt.hist(values, bins=12, color=COLORS['primary'], alpha=0.8, edgecolor='white')
        plt.title(f'Data Distribution: {col}', fontsize=12)
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        out = gdir / f'hist_{col}.png'
        plt.tight_layout(); plt.savefig(out); plt.close()
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
        if len(counts) > 30: continue # Skip if too granular
        
        labels = list(counts.keys()); values = list(counts.values())
        plt.figure(figsize=(10,5))
        plt.bar(labels, values, color=COLORS['warning'])
        plt.xticks(rotation=45, ha='right')
        plt.title(f'Frequency Analysis: {col}')
        out = gdir / f'bar_{col}.png'
        plt.tight_layout(); plt.savefig(out); plt.close()
        paths.append(out)
    return paths

def plot_lines(rows: List[Dict[str, Any]], gdir: Path, logger):
    paths = []
    if not rows: return paths
    types = column_types(rows)
    numeric_cols = [k for k,t in types.items() if t=='numeric']
    date_key = next((c for c in ('date','timestamp','time','created_at') if c in rows[0]), None)
    
    index_labels = [str(r.get(date_key, i)) for i,r in enumerate(rows)]
    for col in numeric_cols:
        values = [safe_float(r.get(col)) for r in rows if safe_float(r.get(col)) is not None]
        if not values: continue
        
        plt.figure(figsize=(9,5))
        plt.plot(index_labels[:len(values)], values, marker='s', color=COLORS['success'], linewidth=2)
        plt.fill_between(index_labels[:len(values)], values, alpha=0.1, color=COLORS['success'])
        plt.title(f'Metric Trend: {col}')
        plt.xticks(rotation=45, ha='right')
        out = gdir / f'line_{col}.png'
        plt.tight_layout(); plt.savefig(out); plt.close()
        paths.append(out)
    return paths

def generate_graphs(rows: List[Dict[str, Any]], static_dir: Path, graph_types: list[str], logger, run_id: str | None = None, extra_data: Dict = None):
    """
    Primary Entry point. 
    Preserves original signature while adding 'extra_data' for high-end graphics.
    """
    gdir = ensure_graph_dir(static_dir, run_id)
    generated = []
    types_norm = [g.strip().lower() for g in graph_types]
    
    # 1. Standard Auto Graphs
    auto = ('auto' in types_norm) or (not types_norm)
    if auto or 'histogram' in types_norm: generated += plot_histograms(rows, gdir, logger)
    if auto or 'bar' in types_norm:       generated += plot_bar_counts(rows, gdir, logger)
    if auto or 'line' in types_norm:      generated += plot_lines(rows, gdir, logger)
    
    # 2. Executive Visuals (if data provided in extra_data)
    if extra_data:
        if 'health_score' in extra_data:
            generated.append(plot_health_gauge(extra_data['health_score'], gdir, logger))
        if 'categories' in extra_data:
            generated.append(plot_radar_chart(extra_data['categories'], gdir, logger, extra_data.get('competitor_cats')))
        if 'security' in extra_data:
            generated.append(plot_security_heatmap(extra_data['security'], gdir, logger))
            
    return generated
