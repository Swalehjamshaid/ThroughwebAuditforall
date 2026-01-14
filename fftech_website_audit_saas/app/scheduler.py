from apscheduler.schedulers.background import BackgroundScheduler
from app.audit.analyzer import run_200_metric_audit
from app.audit.report import generate_professional_pdf
from app.config import settings
import resend

# Initialize the global background scheduler
scheduler = BackgroundScheduler()
resend.api_key = settings.RESEND_API_KEY

async def send_scheduled_audit(user_email, url):
    """
    Background task to run an audit, generate a PDF, and email it to the user.
    """
    # 1. Run the 200-metric deep audit
    results, score = await run_200_metric_audit(url)
    grade = "A+" if score >= 90 else "B"
    
    # 2. Generate the high-fidelity 5-page PDF
    pdf_content = generate_professional_pdf(results, url, score, grade)
    
    # 3. Deliver via Resend API
    resend.Emails.send({
        "from": settings.RESEND_FROM_EMAIL,
        "to": user_email,
        "subject": f"Scheduled FF Tech AI Audit: {url}",
        "attachments": [
            {
                "filename": f"FFTech_Audit_{url.replace('https://', '')}.pdf",
                "content": list(pdf_content)
            }
        ],
        "html": f"<strong>Your scheduled audit for {url} is ready.</strong><br>Find your certified 5-page report attached."
    })

# Start the scheduler if it isn't already running
if not scheduler.running:
    scheduler.start()
