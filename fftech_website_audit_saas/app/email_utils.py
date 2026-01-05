import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.headerregistry import Address

SMTP_HOST     = os.getenv('SMTP_HOST')
SMTP_PORT     = int(os.getenv('SMTP_PORT', '587'))  # 587 STARTTLS, 465 SSL
SMTP_USER     = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
BASE_URL      = os.getenv('BASE_URL', 'http://localhost:8000')
VERIFICATION_PATH = os.getenv('VERIFICATION_PATH', '/auth/verify')
SENDER_NAME   = os.getenv('SENDER_NAME', 'FF Tech')
REPLY_TO      = os.getenv('REPLY_TO', SMTP_USER or '')


def _build_msg_html(to_email: str, token: str) -> MIMEMultipart:
    verify_link = f"{BASE_URL}{VERIFICATION_PATH}?token={token}"
    text_body = (
        "Verify your account\n\n"
        "Please use the link to verify your email:\n"
        f"{verify_link}\n\n"
        "If you didn't request this, you can ignore this message."
    )
    html_body = (
        "<div style='font-family:Segoe UI,Arial,sans-serif;'>"
        "<h3 style='color:#0057D9;margin:0 0 8px'>Verify your account</h3>"
        "<p style='margin:0 0 12px'>Click the button below to verify your email.</p>"
        f"<p><a href='{verify_link}' style='background:#0057D9;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none' target='_blank' rel='noopener'>Verify Email</a></p>"
        "<p style='color:#6b778c'>If you didn’t request this, you can ignore this message.</p>"
        "</div>"
    )
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"{SENDER_NAME} – Verify your account"
    msg['From']    = f"{SENDER_NAME} <{SMTP_USER}>"
    msg['To']      = to_email
    if REPLY_TO:
        msg.add_header('Reply-To', REPLY_TO)
    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))
    return msg


def send_verification_email(to_email: str, token: str) -> bool:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        print("[email_utils] Missing SMTP settings. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD.")
        return False
    msg = _build_msg_html(to_email, token)
    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo(); server.starttls(); server.ehlo()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())
        print(f"[email_utils] Verification email sent to {to_email}")
        return True
    except Exception as e:
        print(f"[email_utils] send_verification_email error: {e}")
        return False
