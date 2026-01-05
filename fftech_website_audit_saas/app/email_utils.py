import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Read variables from environment
SMTP_HOST     = os.getenv('SMTP_HOST')
SMTP_PORT     = int(os.getenv('SMTP_PORT', '587'))  # 587 for STARTTLS, 465 for SSL
SMTP_USER     = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
BASE_URL      = os.getenv('BASE_URL', 'http://localhost:8000')


def send_verification_email(to_email: str, token: str) -> bool:
    """
    Sends a verification email with a clickable link: {BASE_URL}/verify?token=<JWT>
    Returns True on success, False otherwise.
    """
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        return False

    verify_link = f"{BASE_URL}/verify?token={token}"

    # Plain-text fallback
    text_body = (
        "Verify your account\n\n"
        "Please open the following link to verify your email:\n"
        f"{verify_link}\n\n"
        "If you didn't request this, you can ignore this message."
    )

    # HTML body with clickable link
    html_body = (
        "<h3>Verify your account</h3>"
        "<p>Please click the link below to verify your email:</p>"
        f'<p><a href="{verify_link}" target="_blank" rel="noopener noreferrer">{verify_link}</a></p>'
        "<p>If you didn’t request this, you can ignore this message.</p>"
    )

    msg = MIMEMultipart('alternative')
    msg['Subject'] = "Verify your FF Tech account"
    msg['From']    = SMTP_USER
    msg['To']      = to_email
    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    try:
        if SMTP_PORT == 465:
            # SMTPS (implicit SSL)
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())
        else:
            # STARTTLS (explicit TLS)
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"[email_utils] send_verification_email failed: {e}")
        return False
