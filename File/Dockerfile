# Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Virtual env from your original
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY requirements.txt /app/
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 8080

# Exec form + sh -c forces expansion of $PORT
CMD ["sh", "-c", "uvicorn fftech_audit.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
