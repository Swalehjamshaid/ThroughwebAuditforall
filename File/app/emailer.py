
import os, smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from settings import MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM, MAIL_USE_TLS
from datetime import datetime

def send_verification_email(to_email, verify_link, name, data_path):
    subject='Verify your email – FF Tech'
    body=f"Hi {name},

Please click the link to verify your email and complete registration:
{verify_link}

If you did not request this, ignore this email."
    if MAIL_SERVER and MAIL_PORT and MAIL_USERNAME and MAIL_PASSWORD:
        try:
            msg=MIMEText(body,'plain','utf-8'); msg['Subject']=subject; msg['From']=formataddr(('FF Tech',MAIL_FROM)); msg['To']=to_email
            with smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=30) as s:
                if MAIL_USE_TLS: s.starttls()
                s.login(MAIL_USERNAME, MAIL_PASSWORD)
                s.sendmail(MAIL_FROM,[to_email], msg.as_string())
            return True
        except Exception: pass
    outbox=os.path.join(data_path,'outbox'); os.makedirs(outbox, exist_ok=True)
    fname=os.path.join(outbox,f"verify_{to_email.replace('@','_')}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.eml")
    with open(fname,'w',encoding='utf-8') as fh:
        fh.write(f"From: FF Tech <{MAIL_FROM}>
To: {to_email}
Subject: {subject}

{body}")
    return False
