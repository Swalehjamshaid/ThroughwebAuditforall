
# Email.py
# M365 Copilot — Email helper with HTML templating and attachments
# Works with SMTP (LOGIN) with SSL/TLS; designed for sending pipeline outputs (PNG, PPTX, XLSX)
# No third-party dependencies required.

import os
import ssl
import mimetypes
import logging
from typing import List, Optional, Dict, Any, Tuple
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
import smtplib
import datetime

logger = logging.getLogger("EmailClient")
logger.setLevel(logging.INFO)

class EmailClient:
    """
    SMTP Email client supporting:
    - HTML body with inline images (cid)
    - Attachments (PNG, PPTX, XLSX, PDF, etc.)
    - CC, BCC, Reply-To, custom From display name
    """
    def __init__(self,
                 smtp_host: str,
                 smtp_port: int,
                 smtp_user: Optional[str] = None,
                 smtp_pass: Optional[str] = None,
                 use_ssl: bool = True,
                 from_email: Optional[str] = None,
                 from_name: Optional[str] = None,
                 default_cc: Optional[List[str]] = None,
                 default_bcc: Optional[List[str]] = None,
                 reply_to: Optional[str] = None):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_pass = smtp_pass
        self.use_ssl = use_ssl
        self.from_email = from_email or smtp_user
        self.from_name = from_name
        self.default_cc = default_cc or []
        self.default_bcc = default_bcc or []
        self.reply_to = reply_to

        logger.info("EmailClient initialized (host=%s, port=%s, ssl=%s)",
                    smtp_host, smtp_port, use_ssl)

    @staticmethod
    def _guess_mime_type(path: str) -> Tuple[str, str]:
        ctype, _ = mimetypes.guess_type(path)
        if ctype is None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        return maintype, subtype

    def _compose(self,
                 subject: str,
                 to: List[str],
                 html_body: str,
                 text_body: Optional[str] = None,
                 cc: Optional[List[str]] = None,
                 bcc: Optional[List[str]] = None,
                 attachments: Optional[List[str]] = None,
                 inline_images: Optional[Dict[str, str]] = None,
                 headers: Optional[Dict[str, str]] = None) -> EmailMessage:
        msg = EmailMessage()

        # From
        if self.from_name and self.from_email:
            msg["From"] = formataddr((self.from_name, self.from_email))
        elif self.from_email:
            msg["From"] = self.from_email
        else:
            raise ValueError("From email is required")

        # To / CC / BCC
        if not to:
            raise ValueError("At least one recipient required")
        msg["To"] = ", ".join(to)

        cc_list = (cc or []) + self.default_cc
        bcc_list = (bcc or []) + self.default_bcc
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        # Note: BCC is not set in headers; we include it in the send() call.

        # Reply-To
        if self.reply_to:
            msg["Reply-To"] = self.reply_to

        # Subject
        msg["Subject"] = subject

        # Additional headers
        if headers:
            for k, v in headers.items():
                msg[k] = v

        # Text + HTML bodies
        if text_body:
            msg.set_content(text_body)

        # Ensure unique message-ID
        msg_id = make_msgid()
        msg["Message-ID"] = msg_id

        # Add HTML alternative
        msg.add_alternative(html_body, subtype="html")

        # Inline images (cid mapping: cid_name -> file path)
        if inline_images:
            for cid_name, path in inline_images.items():
                try:
                    with open(path, "rb") as f:
                        maintype, subtype = self._guess_mime_type(path)
                        msg.get_payload()[1].add_related(
                            f.read(),
                            maintype=maintype,
                            subtype=subtype,
                            cid=f"<{cid_name}>"
                        )
                        logger.info("Inline image attached: %s (cid=%s)", path, cid_name)
                except Exception as e:
                    logger.error("Failed to attach inline image %s: %s", path, e)

        # File attachments
        if attachments:
            for path in attachments:
                try:
                    with open(path, "rb") as f:
                        maintype, subtype = self._guess_mime_type(path)
                        msg.add_attachment(
                            f.read(),
                            maintype=maintype,
                            subtype=subtype,
                            filename=os.path.basename(path)
                        )
                        logger.info("Attachment added: %s", path)
                except Exception as e:
                    logger.error("Failed to attach file %s: %s", path, e)

        # Store BCC in a private attribute to pass to send
        msg._bcc = bcc_list
        return msg

    def send(self, message: EmailMessage) -> None:
        """
        Sends the EmailMessage using SMTP. BCC recipients are included in RCPTs but not headers.
        """
        recipients = []
        if "To" in message:
            recipients += [r.strip() for r in message["To"].split(",") if r.strip()]
        if "Cc" in message:
            recipients += [r.strip() for r in message["Cc"].split(",") if r.strip()]
        recipients += getattr(message, "_bcc", [])

        logger.info("Sending email to: %s", recipients)
        context = ssl.create_default_context()

        if self.use_ssl:
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context) as server:
                if self.smtp_user and self.smtp_pass:
                    server.login(self.smtp_user, self.smtp_pass)
                server.send_message(message, to_addrs=recipients)
        else:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls(context=context)
                if self.smtp_user and self.smtp_pass:
                    server.login(self.smtp_user, self.smtp_pass)
                server.send_message(message, to_addrs=recipients)

        logger.info("Email sent successfully at %s", datetime.datetime.now().isoformat())

    def send_report(self,
                    to: List[str],
                    subject: str,
                    html_body: str,
                    text_body: Optional[str] = None,
                    cc: Optional[List[str]] = None,
                    bcc: Optional[List[str]] = None,
                    attachments: Optional[List[str]] = None,
                    inline_images: Optional[Dict[str, str]] = None,
                    headers: Optional[Dict[str, str]] = None) -> None:
        msg = self._compose(
            subject=subject,
            to=to,
            html_body=html_body,
            text_body=text_body,
            cc=cc, bcc=bcc,
            attachments=attachments,
            inline_images=inline_images,
            headers=headers
        )
        self.send(msg)


def build_html_template(context: Dict[str, Any]) -> str:
    """
    Returns a visually pleasing HTML email body reflecting Khan's preferences.
    Uses only inline CSS for maximum client compatibility.
    Context keys expected:
      - PROJECT_NAME, RUN_TAG, UI_THEME, COMPANY_NAME
      - USER_NAME, JOB_TITLE, MANAGER, SKIP_MANAGER, OFFICE_LOCATION
      - SUMMARY (str), CARDS (list of dicts with title/value), LINKS (list of {text,href})
      - DATE_STR
    """
    theme = (context.get("UI_THEME") or "light").lower()
    bg = "#0f172a" if theme == "dark" else "#f8fafc"
    card_bg = "#1f2937" if theme == "dark" else "#ffffff"
    text = "#e5e7eb" if theme == "dark" else "#0f172a"
    accent = "#3b82f6"

    cards_html = ""
    for card in context.get("CARDS", []):
        cards_html += f"""
        <div style="flex:1; min-width:200px; background:{card_bg}; border-radius:12px; padding:16px; margin:8px; box-shadow:0 4px 12px rgba(0,0,0,0.08);">
            <div style="font-size:12px; color:{accent}; letter-spacing:0.08em; text-transform:uppercase;">{card.get('title','')}</div>
            <div style="font-size:24px; font-weight:700; color:{text}; margin-top:6px;">{card.get('value','')}</div>
        </div>
        """

    links_html = ""
    for link in context.get("LINKS", []):
        links_html += f"""<a href="{linkk.get('text','Open')}</a>"""

    html = f"""
    <div style="background:{bg}; padding:24px; font-family:Segoe UI, Roboto, Helvetica, Arial, sans-serif; color:{text};">
        <div style="max-width:960px; margin:0 auto;">
            <header style="margin-bottom:24px;">
                <div style="font-size:12px; color:{accent}; letter-spacing:0.08em; text-transform:uppercase;">
                    {context.get('COMPANY_NAME','')} — {context.get('PROJECT_NAME','Operational Report')}
                </div>
                <h1 style="margin:8px 0 0; font-size:28px; color:{text};">
                    {context.get('RUN_TAG','Daily Run')} • {context.get('DATE_STR','')}
                </h1>
                <div style="font-size:13px; opacity:0.8;">
                    {context.get('USER_NAME','')} ({context.get('JOB_TITLE','')}) • Manager: {context.get('MANAGER','')} • Skip: {context.get('SKIP_MANAGER','')}
                </div>
                <div style="font-size:12px; opacity:0.7;">Office: {context.get('OFFICE_LOCATION','')}</div>
            </header>

            <section style="background:{card_bg}; border-radius:12px; padding:16px; margin-bottom:16px;">
                <p style="margin:0; line-height:1.6;">{context.get('SUMMARY','')}</p>
            </section>

            <section style="display:flex; flex-wrap:wrap; align-items:stretch; margin-bottom:8px;">
                {cards_html}
            </section>

            <footer style="margin-top:16px; font-size:12px;">
                {links_html}
            </footer>
        </div>
    </div>
    """
    return html
