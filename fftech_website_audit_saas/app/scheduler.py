from apscheduler.schedulers.background import BackgroundScheduler
from app.audit.analyzer import run_200_metric_audit
from app.audit.report import generate_professional_pdf # Absolute import
from app.config import settings
import resend

scheduler = BackgroundScheduler()

async def send_scheduled_audit(user_email, url):
    """
    Triggers the 200-metric audit and emails the generated PDF.
    """
    # 1. Run Audit
    results, score = await run_200_metric_audit(url)
    grade = "A+" if score >= 90 else "B"
    
    # 2. Generate PDF
    pdf_content = generate_professional_pdf(results, url, score, grade)
    
    # 3. Deliver via Resend
    resend.api_key = settings.RESEND_API_KEY
    resend.Emails.send({
        "from": settings.RESEND_FROM_EMAIL,
        "to": user_email,
        "subject": f"Scheduled FF Tech Report: {url}",
        "attachments": [
            {
                "filename": "FFTech_Audit_Report.pdf",
                "content": list(pdf_content)
            }
        ]
    })

if not scheduler.running:
    scheduler.start()
