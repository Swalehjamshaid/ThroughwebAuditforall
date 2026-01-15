import os
import smtplib
from email.mime.text import MIMEText

FROM_EMAIL = os.getenv('FROM_EMAIL', 'no-reply@fftech.ai')

def send_email_html(to_email: str, subject: str, html: str):
    host = os.getenv('SMTP_HOST')
    user = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASS')
    port = int(os.getenv('SMTP_PORT', '587'))
    if not host or not user or not password:
        # Fallback to console
        print('=== EMAIL (console) ===')
        print('TO:', to_email)
        print('SUBJECT:', subject)
        print(html)
        print('=======================')
        return
    msg = MIMEText(html, 'html')
    msg['Subject'] = subject
    msg['From'] = FROM_EMAIL
    msg['To'] = to_email
    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(FROM_EMAIL, [to_email], msg.as_string())