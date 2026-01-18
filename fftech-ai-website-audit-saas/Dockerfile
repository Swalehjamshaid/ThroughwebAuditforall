FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Expose the port (Railway uses this as a hint)
EXPOSE 8000

# Updated CMD to handle the $PORT environment variable correctly
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
