
# Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Default ENV (override in Railway dashboard as needed)
ENV ENABLE_LIGHTHOUSE=0 \
    MAX_PAGES_MAIN=120 \
    MAX_PAGES_COMP=40 \
    CRAWL_TIMEOUT=15.0 \
    MAX_LINK_CHECKS=150 \
    ACCEPT_LANGUAGE="en-US,en;q=0.8"

EXPOSE 8080

# Run Uvicorn in foreground (PID 1)
CMD ["uvicorn", "fftech_audit.app:app", "--host", "0.0.0.0", "--port", "8080"]
``
