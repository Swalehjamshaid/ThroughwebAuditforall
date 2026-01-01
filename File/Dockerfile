
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY . .

# Default for local runs (Railway injects PORT at runtime)
ENV PORT=8000

# IMPORTANT: Shell-wrapped CMD makes ${PORT} expand before Gunicorn runs
CMD ["/bin/sh", "-c", "exec gunicorn app.main:app -b 0.0.0.0:${PORT} -w 2"]
