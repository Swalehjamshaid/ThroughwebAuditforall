
import pandas as pd
import matplotlib.pyplot as plt
from pptx import Presentation
from pptx.util import Inches


def save_png_summary(cat_scores: dict, path: str):
    labels = list(cat_scores.keys())
    values = [cat_scores[k] for k in labels]
    fig, ax = plt.subplots(figsize=(8, 4), dpi=200)
    ax.bar(labels, values, color='#0AD1A3')
    ax.set_ylim(0, 100)
    ax.set_title('Category Scores')
    fig.tight_layout()
    fig.savefig(path, format='png')
    plt.close(fig)


def save_xlsx(results: dict, path: str):
    rows = []
    for cat, metrics in results.items():
        for mid, data in metrics.items():
            rows.append({'category': cat, 'metric_id': mid, 'score': data.get('score'), 'weight': data.get('weight', 1.0)})
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='metrics')


def save_pptx(overall_score: float, grade: str, cat_scores: dict, png_path: str, path: str):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = 'FF Tech — AI Website Audit'
    slide.placeholders[1].text = f'Overall: {overall_score:.0f}% — {grade}'

    slide2 = prs.slides.add_slide(prs.slide_layouts[5])
    slide2.shapes.title.text = 'Category Scores'
    slide2.shapes.add_picture(png_path, Inches(1), Inches(1.5), height=Inches(4))
    prs.save(path)
