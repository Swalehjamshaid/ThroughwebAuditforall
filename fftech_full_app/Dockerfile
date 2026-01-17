
# fftech_full_app/Dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (psycopg needs libpq headers on some images)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . /app

# Docs only; Railway doesn't rely on EXPOSE
EXPOSE 8000

# Start via Python so we read PORT in Python (no shell expansion)
CMD ["python", "run.py"]
