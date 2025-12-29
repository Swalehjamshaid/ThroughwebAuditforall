
# ---------------- Open Audit (SSR) ----------------
@app.post("/audit/open", response_class=HTMLResponse)
async def audit_open_ssr(request: Request, url: str = Form(...)):
    if not is_valid_url(url):
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": "Invalid URL", "prefill_url": url},
            status_code=400,
        )
    try:
        eng = AuditEngine(url)
        metrics: Dict[int, Dict[str, Any]] = eng.compute_metrics()
    except Exception as e:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": f"Audit failed: {e}", "prefill_url": url},
            status_code=500,
        )

    score = metrics[1]["value"]
    grade = metrics[2]["value"]
    summary = metrics[3]["value"]
    category = metrics[8]["value"]
    severity = metrics[7]["value"]

    rows: List[Dict[str, Any]] = []
    for pid in range(1, 201):
        desc = METRIC_DESCRIPTORS.get(pid, {"name": "(Unknown)", "category": "-"})
        cell = metrics.get(pid, {"value": "N/A", "detail": ""})
        val = cell["value"]
        if isinstance(val, (dict, list)):
            try:
                val = json.dumps(val, ensure_ascii=False)
            except Exception:
                val = str(val)
        rows.append({
            "id": pid,
            "name": desc["name"],
            "category": desc["category"],
            "value": val,
            "detail": cell.get("detail", "")
        })

    allow_pdf = False
    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "url": url,
            "score": score,
            "grade": grade,
            "summary": summary,
            "severity": severity,
            "category": category,
            "rows": rows,
            "allow_pdf": allow_pdf,
            "build_marker": "v2025-12-28-SSR-3",
        },
    )
