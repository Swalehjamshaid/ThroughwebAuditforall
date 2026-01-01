FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1
WORKDIR /app

# Install dependencies
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Set default port
ENV PORT=8000

# FIX: Use Shell Form (no brackets) so $PORT is translated to 8000
CMD gunicorn app.main:app -b 0.0.0.0:$PORT -w 2
