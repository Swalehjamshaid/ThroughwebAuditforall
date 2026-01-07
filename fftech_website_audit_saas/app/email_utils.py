
# app/email_utils.py
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
DEBUG_SMTP    = os.getenv("DEBUG_SMTP", "0").lower() in ("1", "true")


def _build_absolute_url(path: str) -> str:
    """Build a robust absolute URL that won’t produce double slashes."""
    return f"{BASE_URL.rstrip('/')}/{path.lstrip('/')}"


# -----------------------------
# Email: Verification (existing)
# -----------------------------
def send_verification_email(to_email: str, token: str) -> bool:
    """
    Sends an email verification link to the user.
    Returns True on success, False on failure (with log messages).
    """
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        print("[email] Missing SMTP env vars (SMTP_HOST/SMTP_USER/SMTP_PASSWORD).")
        return False

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
        {verify_link}
          Verify Email
        </a>
      </p>
      <p style="color:#666;margin-top:12px">If the button doesn’t work, paste this link in your browser:</p>
      <p><code style="word-break:break-all">{verify_link}</code></p>
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
            import ssl
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=25) as server:
                if DEBUG_SMTP: server.set_debuglevel(1)
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())
        else:
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
        print(f"[email] SMTP auth failed: {e}. Hint: Gmail/Outlook with MFA -> use an App Password.")
        return False
    except smtplib.SMTPConnectError as e:
        print(f"[email] SMTP connect error: {e}. Check network/firewall and port {SMTP_PORT}.")
        return False
    except smtplib.SMTPServerDisconnected as e:
        print(f"[email] SMTP disconnected: {e}. Verify TLS/SSL settings match the port.")
        return False
    except Exception as e:
        print(f"[email] General SMTP error: {e}")
        return False


# --------------------------------
# Email: Magic Login (new function)
# --------------------------------
def send_magic_login_email(to_email: str, token: str) -> bool:
    """
    Sends the passwordless 'magic login' link to the user.
    Returns True on success, False on failure (with log messages).
    """
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        print("[smtp] Missing SMTP configuration (SMTP_HOST/SMTP_USER/SMTP_PASSWORD).")
        return False

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

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = to_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if SMTP_PORT == 465:
            import ssl
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=25) as server:
                if DEBUG_SMTP: server.set_debuglevel(1)
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=25) as server:
                if DEBUG_SMTP: server.set_debuglevel(1)
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())

        print(f"[smtp] Magic link email sent to {to_email} with link: {login_link}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        print(f"[smtp] Authentication failed: {e}. Hint: Gmail/Outlook with MFA -> use App Password.")
        return False
    except smtplib.SMTPConnectError as e:
        print(f"[smtp] Connect error: {e}. Check network/firewall and port {SMTP_PORT}.")
        return False
    except smtplib.SMTPServerDisconnected as e:
        print(f"[smtp] Server disconnected: {e}. Verify TLS/SSL settings and port.")
        return False
    except Exception as e:
        print(f"[smtp] General error sending magic link: {e}")
        return False
