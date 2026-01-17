
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd
from typing import Dict, Any


def export_graphs(audit_id: int, category_scores: Dict[str, float], out_dir: str) -> str:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    img_path = out / f"audit_{audit_id}_scores.png"
    labels = list(category_scores.keys())
    values = list(category_scores.values())
    plt.figure(figsize=(6,4))
    plt.bar(labels, values, color="#3b82f6")
    plt.title("Category Scores")
    plt.ylim(0, 100)
    plt.tight_layout()
    plt.savefig(img_path)
    plt.close()
    return str(img_path)


def export_xlsx(audit_id: int, metrics: Dict[str, Any], category_scores: Dict[str, float], out_dir: str) -> str:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    xlsx_path = out / f"audit_{audit_id}.xlsx"
    df_metrics = pd.DataFrame([metrics])
    df_scores = pd.DataFrame([category_scores])
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df_metrics.to_excel(writer, index=False, sheet_name="metrics")
        df_scores.to_excel(writer, index=False, sheet_name="scores")
    return str(xlsx_path)


def export_pptx(audit_id: int, graph_png_path: str, metrics: Dict[str, Any], out_dir: str) -> str:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    html_path = out / f"audit_{audit_id}.html"
    rows = ''.join(f"<li><b>{k}</b>: {v}</li>" for k, v in metrics.items())
    html = f"""
    <html><body>
    <h2>Audit {audit_id} Summary</h2>
    <img src="{Path(graph_png_path).name}" style="max-width:600px" />
    <ul>{rows}</ul>
    </body></html>
    """
    html_path.write_text(html, encoding="utf-8")
    return str(html_path)
