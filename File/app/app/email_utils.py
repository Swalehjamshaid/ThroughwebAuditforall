
import os
import smtplib
from email.message import EmailMessage

MAIL_FROM = os.getenv('MAIL_FROM', 'no-reply@fftech.example')
SMTP_HOST = os.getenv('SMTP_HOST', 'localhost')
SMTP_PORT = int(os.getenv('SMTP_PORT', '25'))
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASS = os.getenv('SMTP_PASS')


def send_email(to: str, subject: str, body: str, attachments=None):
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = MAIL_FROM
    msg['To'] = to
    msg.set_content(body)

    for att in attachments or []:
        with open(att, 'rb') as f:
            data = f.read()
        msg.add_attachment(data, maintype='application', subtype='pdf', filename=os.path.basename(att))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        if SMTP_USER and SMTP_PASS:
            try:
                smtp.starttls()
            except Exception:
                pass
            smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)
