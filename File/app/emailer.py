
import os

def send_verification_email(email: str, verify_link: str, name: str, data_path: str):
    # Demo only: write the email to an outbox file instead of actually sending.
    outbox = os.path.join(data_path, 'outbox')
    os.makedirs(outbox, exist_ok=True)
    msg = f"To: {email}
Subject: Verify your email
Hello {name}, click to verify: {verify_link}
"
    with open(os.path.join(outbox, f"verify-{email.replace('@','_')}.txt"), 'w', encoding='utf-8') as f:
        f.write(msg)
