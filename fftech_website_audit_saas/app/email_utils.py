
# app/email_utils.py
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

UI_BRAND_NAME = os.getenv("UI_BRAND_NAME", "FF Tech")
BASE_URL      = os.getenv("BASE_URL", "http://localhost:8000")

SMTP_HOST     = os.getenv("SMTP_HOST")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))  # 587 (STARTTLS/TLS) or 465 (SSL)
SMTP_USER     = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
DEBUG_SMTP    = os.getenv("DEBUG_SMTP", "0").lower() in ("1", "true")


def _build_absolute_url(path: str) -> str:
    """Build an absolute URL safely (no double slashes)."""
    return f"{BASE_URL.rstrip('/')}/{path.lstrip('/')}"


def _send_email(to_email: str, subject: str, text_body: str, html_body: str) -> bool:
    """Low-level SMTP sender with TLS/SSL handling and robust logging."""
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        print("[email] Missing SMTP env vars (SMTP_HOST/SMTP_USER/SMTP_PASSWORD).")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = to_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if SMTP_PORT == 465:
            import ssl
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=25) as s:
                if DEBUG_SMTP: s.set_debuglevel(1)
                s.login(SMTP_USER, SMTP_PASSWORD)
                s.sendmail(SMTP_USER, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=25) as s:
                if DEBUG_SMTP: s.set_debuglevel(1)
                s.ehlo()
                s.starttls()
                s.ehlo()
                s.login(SMTP_USER, SMTP_PASSWORD)
                s.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True

    except smtplib.SMTPAuthenticationError as e:
        print(f"[email] SMTP auth failed: {e}. Tip: Gmail/Outlook with MFA -> use App Password.")
        return False
    except smtplib.SMTPConnectError as e:
        print(f"[email] SMTP connect error: {e}. Check network/firewall and port {SMTP_PORT}.")
        return False
    except smtplib.SMTPServerDisconnected as e:
        print(f"[email] SMTP disconnected: {e}. Verify TLS/SSL settings and port.")
        return False
    except Exception as e:
        print(f"[email] General SMTP error: {e}")
        return False


# ---------- Verification ----------
def send_verification_email(to_email: str, token: str) -> bool:
    verify_link = _build_absolute_url(f"auth/verify?token={token}")
    subject = f"{UI_BRAND_NAME} – Verify your account"

    text_body = (
        f"{UI_BRAND_NAME} — Verify your account\n\n"
        f"Click the link to verify:\n{verify_link}\n\n"
        "If you didn’t request this, you can ignore this email."
    )
    html_body = f"""
    <div style="font-family:system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;line-height:1.5">
      <h2 style="margin:0 0 8px">{UI_BRAND_NAME}</h2>
      <p>Thanks for signing up! Please verify your account:</p>
      <p>
        <a href="{verify_link}" target="_blank" rel="noopener noreferrer"
           style="display:inline-block;background:#5B8CFF;color:#fff;padding:10px 16px;border-radius:6px      <p><code style="word-break:break-all">{verify_link}</code></p>
    </div>
    """

    ok = _send_email(to_email, subject, text_body, html_body)
    print(f"[email] Verification email {'SENT' if ok else 'FAILED'} to {to_email} | link={verify_link}")
    return ok


# ---------- Magic Login ----------
def send_magic_login_email(to_email: str, token: str) -> bool:
    login_link = _build_absolute_url(f"auth/magic?token={token}")
    subject = f"{UI_BRAND_NAME} — Magic Login Link"

    text_body = (
        f"{UI_BRAND_NAME} — Magic Login\n\n"
        f"Use this link to sign in:\n{login_link}\n\n"
        "If you didn’t request this, you can ignore this email."
    )
    html_body = f"""
    <h3>{UI_BRAND_NAME} — Magic Login</h3>
    <p>Hello!</p>
    <p>Click the secure link below to log in:</p>
    <p>{login_link}{login_link}</a></p>
    <p>This link will expire shortly. If you didn't request it, you can ignore this message.</p>
    """

    ok = _send_email(to_email, subject, text_body, html_body)
    print(f"[email] Magic link {'SENT' if ok else 'FAILED'} to {to_email} | link={login_link}")
    return ok
