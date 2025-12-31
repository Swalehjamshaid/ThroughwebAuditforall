# Dockerfile (improved version)
FROM python:3.11-slim

# Prevent writing .pyc files and buffer output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create non-root user (recommended for security on Railway)
RUN adduser --disabled-password --gecos '' appuser
WORKDIR /app
COPY . /app

# Install dependencies as root
RUN pip install --no-cache-dir -r requirements.txt

# Switch to non-root user
USER appuser

# Environment variables (good as-is)
ENV ENABLE_LIGHTHOUSE=0 \
    MAX_PAGES_MAIN=120 \
    MAX_PAGES_COMP=40 \
    CRAWL_TIMEOUT=15.0 \
    MAX_LINK_CHECKS=150 \
    ACCEPT_LANGUAGE="en-US,en;q=0.8"

# Use Railway's PORT env var
EXPOSE 8080
CMD ["bash", "-lc", "uvicorn fftech_audit.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
