# Dockerfile
FROM python:3.11-slim

# Python best practices
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Optional: Use virtual env (kept from your original)
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install dependencies efficiently
COPY requirements.txt /app/
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . /app

# Expose (informational only)
EXPOSE 8080

# CRITICAL: Use SHELL FORM (no brackets) so $PORT is expanded by bash
CMD uvicorn fftech_audit.app:app --host 0.0.0.0 --port ${PORT:-8080}
