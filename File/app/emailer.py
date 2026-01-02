
import os

def send_verification_email(email, verify_link, name, data_path):
    # Dev stub: write a file in data/ so you can click the link
    os.makedirs(data_path, exist_ok=True)
    with open(os.path.join(data_path, f'verify_{email}.txt'), 'w', encoding='utf-8') as f:
        f.write(f"Hi {name}, verify here: {verify_link}\n")
``
