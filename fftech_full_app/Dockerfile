FROM python:3.11-slim

# Prevent Python from writing .pyc files and keep logs snappy
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your app
COPY . /app

# IMPORTANT: No brackets []. This allows $PORT to be injected.
CMD uvicorn backend.main:app --host 0.0.0.0 --port $PORT
