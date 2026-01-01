
# app/emailer.py
import os

def send_verification_email(email: str, verify_link: str, name: str, data_path: str):
    """
    Demo email sender: writes a 'verification email' to an outbox file
    instead of actually sending via SMTP. This avoids external dependencies
    and keeps Railway deployment simple.

    Args:
        email (str): Recipient email address.
        verify_link (str): Unique verification URL.
        name (str): Recipient name.
        data_path (str): Path to the app's data directory (e.g., app/data).
    """
    # Ensure the outbox directory exists
    outbox = os.path.join(data_path, 'outbox')
    os.makedirs(outbox, exist_ok=True)

    # ✅ Fixed: properly terminated f-string with newline characters
    msg = (
        f"To: {email}\n"
        f"Subject: Verify your email\n"
        f"Hello {name}, click to verify: {verify_link}\n"
    )

    # Write the message to a file named after the recipient (safe for filesystem)
    safe_name = email.replace('@', '_')
    file_path = os.path.join(outbox, f"verify-{safe_name}.txt")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(msg)
