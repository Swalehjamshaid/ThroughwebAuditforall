from flask_mail import Message
from .models import db, Website, Audit
from . import mail

def send_audit_email(website_id, audit_id):
    website = Website.query.get(website_id)
    audit = Audit.query.get(audit_id)
    user = website.owner
    if not user or not user.email:
        return
    msg = Message(
        subject=f"Audit Report ({website.url}) – Overall {audit.score_overall}",
        recipients=[user.email]
    )
    msg.body = f"""Hello,

Your audit has completed.

URL: {website.url}
Overall Score: {audit.score_overall}
Performance: {audit.score_perf}
Accessibility: {audit.score_accessibility}
Best Practices: {audit.score_best_practices}
SEO: {audit.score_seo}

Regards,
WebAudit SaaS
"""
    mail.send(msg)
