# Dockerfile
ARG PYTHON_VERSION=3.11-slim
FROM python:${PYTHON_VERSION}

# Prevent Python from writing .pyc files and buffer output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create and use virtual environment (best practice)
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy only requirements first for better layer caching
COPY requirements.txt /app/

# Create venv and install dependencies
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . /app

# Expose port (informational only; Railway ignores this)
EXPOSE 8080

# Start Uvicorn using shell form so $PORT and ${PORT:-8080} are expanded correctly
CMD uvicorn fftech_audit.app:app --host 0.0.0.0 --port ${PORT:-8080}
