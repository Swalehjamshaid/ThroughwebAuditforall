# Dockerfile
FROM python:3.11-slim

# Python best practices (no .pyc files, unbuffered output)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Virtual environment path (from your original setup)
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt /app/

# Create venv and install dependencies
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy the rest of your app code
COPY . /app

# Expose port (informational; Railway ignores this)
EXPOSE 8080

# FIXED CMD: Use sh -c for shell expansion of $PORT
CMD ["sh", "-c", "uvicorn fftech_audit.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
