@app.post("/audits/{website_id}/run")
def run_audit(website_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = _get_user_id(request, db)
    
    # Enforce 10 Audit Limit for Free Users
    sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()
    if sub.plan == "free" and sub.quota_used >= sub.quota_limit:
        raise HTTPException(status_code=402, detail="10 Audit limit reached. Upgrade for $5 USD Monthly.")

    # Execute Audit
    w = db.query(Website).filter(Website.id == website_id).first()
    metrics = run_basic_audit(w.url)
    score, grade = strict_score(metrics)
    summary = generate_summary_200(metrics, score, grade)
    
    # Save to Railway
    a = Audit(website_id=w.id, grade=grade, overall_score=score, 
              summary_200_words=summary, json_metrics=metrics)
    db.add(a)
    sub.quota_used += 1 # Update count
    db.commit()
    
    return {"audit_id": a.id, "grade": grade, "score": score, "summary": summary}
