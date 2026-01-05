
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Read variables from environment (Railway → Variables)
SMTP_HOST     = os.getenv('SMTP_HOST')
SMTP_PORT     = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER     = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
BASE_URL      = os.getenv('BASE_URL', 'http://localhost:8000')  # e.g., https://your-service.up.railway.app

def send_verification_email(to_email: str, token: str) -> bool:
    """
    Sends a verification email with a clickable link: {BASE_URL}/verify?token=<JWT>
    Returns True on success, False otherwise.
    """

    # If SMTP is not configured, skip without breaking registration.
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        return False

    verify_link = f"{BASE_URL}/verify?token={token}"

    # Build HTML body
    html_lines = [
        "<h3>Verify your account</h3>",
        "<p>Please click the link below to verify your email:</p>",
        f'<p>{verify_link}{verify_link}</a></p>',
        "<p>If you didn't request this, you can ignore this message.</p>",
    ]
    html_body = "\n".join(html_lines)

    # (Optional) Plain-text version for clients that don't support HTML
    text_body = (
        "Verify your account\n\n"
        "Please open the following link to verify your email:\n"
        f"{verify_link}\n\n"
        "If you didn't request this, you can ignore this message."
    )

    msg = MIMEMultipart('alternative')
    msg['Subject'] = "Verify your FF Tech account"
    msg['From']    = SMTP_USER
    msg['To']      = to_email
    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            # Use STARTTLS on port 587; for SMTPS (465), you'd use SMTP_SSL
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception:
        # Do not crash the app on SMTP errors—return False so caller can continue gracefully.
        return False
