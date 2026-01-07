
# fftech_website_audit_saas/app/email_utils.py
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL      = os.getenv("BASE_URL", "http://localhost:8000")

SMTP_HOST     = os.getenv("SMTP_HOST")              # e.g., smtp.gmail.com / smtp.office365.com / smtp.sendgrid.net
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))  # 587 (STARTTLS/TLS) or 465 (SSL)
SMTP_USER     = os.getenv("SMTP_USER")              # full email address or SMTP username
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")          # app password if MFA enabled

# Enable verbose SMTP conversation (0/1/true/TRUE)
DEBUG_SMTP    = os.getenv("DEBUG_SMTP", "0").lower() in ("1", "true")

def _build_verify_link(token: str) -> str:
    """
    Build a robust verification URL that won’t produce double slashes.
    """
    return f"{BASE_URL.rstrip('/')}/auth/verify?token={token}"

def send_verification_email(to_email: str, token: str) -> bool:
    """
    Sends a verification email. Returns True on success, False on failure.
    Emits clear logs to aid troubleshooting.
    """
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        print("[email] Missing SMTP env vars (SMTP_HOST/SMTP_USER/SMTP_PASSWORD).")
        return False

    verify_link = _build_verify_link(token)
    subject = f"{UI_BRAND_NAME} – Verify your account"

    # Plain-text fallback improves deliverability
    text_body = (
        f"{UI_BRAND_NAME} — Verify your account\n\n"
        f"Click the link to verify:\n{verify_link}\n\n"
        "If you didn’t request this, you can ignore this email."
    )

    # Clean HTML (no broken attributes)
    html_body = f"""
    <div style="font-family:system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;line-height:1.5">
      <h2 style="margin:0 0 8px">{UI_BRAND_NAME}</h2>
      <p>Thanks for signing up! Please verify your account:</p>
      <p>
        <a href="{verify_link}" target="_blank" rel="noopener noreferrer"
           style="display:inline-block;background:#5B8CFF;color:#fff;padding:10px 16px;
                  border-radius:6px;textrd-break:break-all">{verify_link}</code></p>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = to_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if SMTP_PORT == 465:
            # Implicit SSL
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=25) as server:
                if DEBUG_SMTP: server.set_debuglevel(1)
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())
        else:
            # STARTTLS (recommended for 587)
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=25) as server:
                if DEBUG_SMTP: server.set_debuglevel(1)
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())

        print(f"[email] Verification email sent to {to_email} with link: {verify_link}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        print(f"[email] SMTP auth failed: {e}. "
              "If using Gmail/Outlook with MFA, generate an App Password and use it.")
        return False

    except smtplib.SMTPConnectError as e:
        print(f"[email] SMTP connect error: {e}. Check network, firewall, and that port {SMTP_PORT} is allowed.")
        return False

    except smtplib.SMTPServerDisconnected as e:
        print(f"[email] SMTP disconnected: {e}. Verify STARTTLS/SSL choice matches the port and provider.")
        return False

    except Exception as e:
        print(f"[email] General SMTP error: {e}")
        return False
