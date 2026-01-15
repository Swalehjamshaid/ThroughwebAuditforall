
import os, smtplib
from email.mime.text import MIMEText

def send_email(to_email: str, subject: str, body: str):
    host = os.getenv('SMTP_HOST')
    user = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASS')
    from_email = os.getenv('FROM_EMAIL', 'no-reply@fftech.ai')
    if not host or not user or not password:
        print('=== EMAIL (console) ===')
        print('TO:', to_email)
        print('SUBJECT:', subject)
        print(body)
        print('=======================')
        return
    msg = MIMEText(body, 'html')
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = to_email
    with smtplib.SMTP(host, int(os.getenv('SMTP_PORT', '587'))) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(from_email, [to_email], msg.as_string())
