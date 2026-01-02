
import os

def send_verification_email(email: str, verify_link: str, name: str, data_path: str) -> None:
    """
    Development stub: writes a local file containing the verification link.
    In production, integrate an email provider (SMTP/API).
    """
    os.makedirs(data_path, exist_ok=True)
    file_path = os.path.join(data_path, f'verify_{email}.txt')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(f"Hi {name},\n\nPlease verify your account:\n{verify_link}\n")
