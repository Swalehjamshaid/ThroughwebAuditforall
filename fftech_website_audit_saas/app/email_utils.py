
# fftech_website_audit_saas/app/email_utils.py
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL      = os.getenv("BASE_URL", "http://localhost:8000")

SMTP_HOST     = os.getenv("SMTP_HOST")              # e.g., smtp.gmail.com / smtp.office365.com
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))  # 587 (STARTTLS) or 465 (SSL)
SMTP_USER     = os.getenv("SMTP_USER")              # full email address for the account
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")          # app password if MFA enabled

DEBUG_SMTP    = bool(os.getenv("DEBUG_SMTP", "0") in ("1", "true", "TRUE"))

def _build_verify_link(token: str) -> str:
    # Keep the route consistent with your app
    return f"{BASE_URL}/auth/verify?token={token}"

def send_verification_email(to_email: str, token: str) -> bool:
    """
    Sends a verification email. Returns True on success, False on failure.
    Emits clear logs to aid troubleshooting. No changes to signature to keep main.py integration intact.
    """
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        print("[email] Missing SMTP env vars (SMTP_HOST/SMTP_USER/SMTP_PASSWORD).")
        return False

    verify_link = _build_verify_link(token)
    subject = f"{UI_BRAND_NAME} – Verify your account"
    html_body = f"""
    <div style="font-family:system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;line-height:1.5">
      <h2 style="margin:0 0 8px">{UI_BRAND_NAME}</h2>
      <p>Thanks for signing up! Please verify your account:</p>
      <p><a href="{verify_link}" target="_blank" rel="noopener noreferrer"
            style="display:inline-block;background:#5B8CFF;color:#fffto your browser:<br>
         <code>{verify_link}</code>
      </p>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        if SMTP_PORT == 465:
            # Implicit SSL
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                if DEBUG_SMTP: server.set_debuglevel(1)
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())
        else:
            # STARTTLS (recommended for 587)
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                if DEBUG_SMTP: server.set_debuglevel(1)
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())
        print(f"[email] Verification email sent to {to_email}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        print(f"[email] SMTP auth failed: {e}. "
              "If using Gmail/Outlook with MFA, generate an App Password and use it here.")
        return False

    except smtplib.SMTPConnectError as e:
        print(f"[email] SMTP connect error: {e}. Check firewall/ISP, and ensure port {SMTP_PORT} is allowed.")
        return False

    except smtplib.SMTPServerDisconnected as e:
        print(f"[email] SMTP disconnected: {e}. Check encryption (STARTTLS vs SSL) and correct port.")
        return False

    except Exception as e:
        print(f"[email] General SMTP error: {e}")
        return False
