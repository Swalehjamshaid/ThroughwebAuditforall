
import os, smtplib
from email.mime.text import MIMEText

FROM_EMAIL = os.getenv('FROM_EMAIL', 'no-reply@fftech.ai')

def send_email(to_email: str, subject: str, html_body: str):
    host = os.getenv('SMTP_HOST')
    user = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASS')
    port = int(os.getenv('SMTP_PORT', '587'))
    if not host or not user or not password:
        # Console fallback
        print('=== EMAIL (console) ===')
        print('TO:', to_email)
        print('SUBJECT:', subject)
        print(html_body)
        print('=======================')
        return
    msg = MIMEText(html_body, 'html')
    msg['Subject'] = subject
    msg['From'] = FROM_EMAIL
    msg['To'] = to_email
    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(user, password)
        s.sendmail(FROM_EMAIL, [to_email], msg.as_string())
