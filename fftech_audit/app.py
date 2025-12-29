
@app.post("/audit/open", response_class=HTMLResponse)
async def audit_open_ssr(request: Request, url: str = Form(...)):
    eng = AuditEngine(url)
    metrics = eng.compute_metrics()

    score = metrics[1]["value"]
    grade = metrics[2]["value"]
    summary = metrics[3]["value"]
    severity = metrics[7]["value"]
    category = metrics[8]["value"]  # dict: {"Crawlability":..,"On-Page SEO":..,"Performance":..,"Security":..,"Mobile":..}

    # ✅ Add these lists for template
    strengths = metrics[4]["value"]
    weaknesses = metrics[5]["value"]
    priority_fixes = metrics[6]["value"]

    rows = []
    for pid in range(1, 201):
        desc = METRIC_DESCRIPTORS.get(pid, {"name": f"Metric {pid}", "category": "-"})
        cell = metrics.get(pid, {"value": "N/A", "detail": ""})
        val = cell["value"]
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)
        rows.append({
            "id": pid,
            "name": desc["name"],
            "category": desc["category"],
            "value": val,
            "detail": cell.get("detail", "")
        })

    ctx = {
        "request": request,
        "url": url,
        "score": score,
        "grade": grade,
        "summary": summary,
        "severity": severity,
        "category_scores": category,       # ✅ Fix for template
        "category_json": json.dumps(category),
        "strengths": strengths,            # ✅ For strengths section
        "weaknesses": weaknesses,          # ✅ For weaknesses section
        "priority_fixes": priority_fixes,  # ✅ For priority fixes section
        "rows": rows
    }

    return templates.TemplateResponse("results.html", ctx)
