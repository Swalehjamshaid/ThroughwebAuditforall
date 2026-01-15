
import os
import pandas as pd
import matplotlib.pyplot as plt
from pptx import Presentation
from pptx.util import Inches

def export_graph(audit_id: int, cats: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, f'audit_{audit_id}_categories.png')
    plt.figure(figsize=(8,4)); plt.bar(cats.keys(), cats.values(), color='#22c55e'); plt.xticks(rotation=30, ha='right'); plt.tight_layout(); plt.savefig(p); plt.close(); return p

def export_xlsx(audit_id: int, metrics: dict, cats: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, f'audit_{audit_id}.xlsx')
    with pd.ExcelWriter(p, engine='openpyxl') as w:
        pd.DataFrame([metrics]).to_excel(w, index=False, sheet_name='Metrics')
        pd.DataFrame([cats]).to_excel(w, index=False, sheet_name='CategoryScores')
    return p

def export_pptx(audit_id: int, png_chart: str, metrics: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, f'audit_{audit_id}.pptx')
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0]); slide.shapes.title.text = 'FF Tech – Website Audit Summary'; slide.placeholders[1].text = f'Audit ID: {audit_id}'
    slide = prs.slides.add_slide(prs.slide_layouts[5]); slide.shapes.add_picture(png_chart, Inches(1), Inches(1.2), width=Inches(8))
    slide = prs.slides.add_slide(prs.slide_layouts[5]); tf = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(5)).text_frame; tf.text = 'Key Metrics:'
    for k,v in metrics.items(): pgh = tf.add_paragraph(); pgh.text = f'{k}: {v}'; pgh.level = 1
    prs.save(p); return p
