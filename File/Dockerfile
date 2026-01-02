# Official slim Python image
FROM python:3.12-slim

# Prevent apt prompts + better Python logging
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Working directory
WORKDIR /app

# Copy ONLY the contents of File/app/ → this is where your code lives
COPY File/app/ .

# Install dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# Port (Railway sets $PORT)
ENV PORT=8000

# Start command - your Flask app is in main.py with variable 'app'
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --log-level info \
    main:app"]
