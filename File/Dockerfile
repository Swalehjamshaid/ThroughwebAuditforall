# Dockerfile
ARG PYTHON_VERSION=3.11-slim
FROM python:${PYTHON_VERSION}

# Environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Use virtual environment (good practice)
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install dependencies (better caching)
COPY requirements.txt /app/
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app

# Expose port (informational only)
EXPOSE 8080

# Critical fix: Use SHELL FORM so $PORT is expanded by the shell
CMD uvicorn fftech_audit.app:app --host 0.0.0.0 --port ${PORT:-8080}
