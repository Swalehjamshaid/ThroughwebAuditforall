
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Read variables from environment (Railway → Variables)
SMTP_HOST     = os.getenv('SMTP_HOST')
SMTP_PORT     = int(os.getenv('SMTP_PORT', '587'))  # 587 = STARTTLS, 465 = SSL
SMTP_USER     = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
BASE_URL      = os.getenv('BASE_URL', 'http://localhost:8000')  # e.g., https://your-app.up.railway.app

def send_verification_email(to_email: str, token: str) -> bool:
    """
    Sends a verification email that includes a clickable link:
    {BASE_URL}/verify?token=<JWT>
    Returns True on success, False otherwise.
    """
    # If SMTP is not configured, skip without breaking registration.
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        print("[email_utils] Missing SMTP env vars; email not sent.")
        return False

    verify_link = f"{BASE_URL}/verify?token={token}"

    # Plain-text fallback (for clients that don't render HTML)
    text_body = (
        "Verify your account\n\n"
        "Please open the following link to verify your email:\n"
        f"{verify_link}\n\n"
        "If you didn't request this, you can ignore this message."
    )

    # HTML body with a proper clickable anchor (no escaped entities)
    html_body = (
        "<h3>Verify your account</h3>"
        "<p>Please click the link below to verify your email:</p>"
        f'<p><a href="{verify_link}" target="_>'
        "<p>If you didn’t request this, you can ignore this message.</p>"
    )

    # Build the email
    msg = MIMEMultipart('alternative')
    msg['Subject'] = "Verify your FF Tech account"
    msg['From']    = SMTP_USER
    msg['To']      = to_email
    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    try:
        # Use SSL on port 465, else STARTTLS (commonly port 587)
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception as e:
        # Log the exact reason to Railway logs for quick diagnosis
        print(f"[email_utils] send_verification_email failed: {e}")
        return False
