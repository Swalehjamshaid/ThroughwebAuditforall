
FROM python:3.11-slim

WORKDIR /app

# Install dependencies FIRST for better layer caching
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy source last
COPY . .

# Local default; Railway injects PORT at runtime
ENV PORT=8000

# IMPORTANT: Shell-wrapped CMD so ${PORT} expands before Gunicorn starts
# See Railway docs on Start Command for Dockerfile/image services.
CMD ["/bin/sh", "-c", "exec gunicorn app.main:app -b 0.0.0.0:${PORT} -w 2"]
