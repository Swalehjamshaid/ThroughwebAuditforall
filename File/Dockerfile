
FROM python:3.11-slim

WORKDIR /app

# Install dependencies BEFORE copying the whole app (better layer caching)
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the rest of your source
COPY . .

# Default for local runs (Railway injects PORT at runtime)
ENV PORT=8000

# Shell-wrapped CMD ensures ${PORT} expands
CMD ["/bin/sh", "-c", "exec gunicorn app.main:app -b 0.0.0.0:${PORT} -w 2"]
``
