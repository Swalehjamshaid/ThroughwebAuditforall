
# app/main.py
from flask import Flask, request, jsonify

# If you're sending emails, uncomment the next imports:
# from email.message import EmailMessage
# import smtplib
# import os

app = Flask(__name__)

@app.get("/health")
def health():
    return jsonify({"status": "ok"})

@app.post("/send")
def send():
    """
    Example endpoint to demonstrate fixing the unterminated f-string.
    Expects JSON like: {"name": "Khan"}
    """
    data = request.get_json(force=True) or {}
    name = data.get("name", "there")

    # ✅ Fixed multi-line f-string (properly terminated)
    msg_body = f"""Hello {name},

Thank you for reaching out. We received your request and will get back to you shortly.

Best regards,
Support Team"""

    # If you're using EmailMessage to send an email, uncomment this section:
    # msg = EmailMessage()
    # msg["Subject"] = "Thanks for contacting us"
    # msg["From"] = os.getenv("MAIL_FROM", "no-reply@example.com")
    # msg["To"] = os.getenv("MAIL_TO", "support@example.com")
    # msg.set_content(msg_body)
    #
    # # Example SMTP send (adjust host, port, and auth to your provider)
    # with smtplib.SMTP(os.getenv("SMTP_HOST", "localhost"), int(os.getenv("SMTP_PORT", "25"))) as smtp:
    #     # If your SMTP server requires login:
    #     # smtp.starttls()
    #     # smtp.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
    #     smtp.send_message(msg)

    # For demonstration, just return the content
    return jsonify({"message": msg_body})

# Gunicorn entry point: `app.main:app`
# Run locally or in your container with:
#   gunicorn app.main:app --bind 0.0.0.0:8000 --workers 2
