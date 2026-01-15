# Use official Python 3.13 slim base
FROM python:3.13-slim

# Install all required native libraries for WeasyPrint and Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core rendering libraries
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    # GLib & GObject (fixes libgobject-2.0-0 error)
    libglib2.0-0 \
    gobject-introspection \
    # Font & text support
    fontconfig \
    libfreetype6 \
    libharfbuzz0b \
    # Image support
    libjpeg62-turbo \
    libpng16-16 \
    zlib1g \
    # XML & utilities
    libxml2 \
    libxslt1.1 \
    shared-mime-info \
    libffi-dev \
    # Requirements for Playwright/Browsers
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (if using Playwright for the audit)
RUN playwright install --with-deps chromium

# Copy the rest of the application
COPY . .

# IMPORTANT: Use Shell form (no brackets) to ensure $PORT is evaluated
# This fixes the "Invalid value for --port: $PORT" error
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
