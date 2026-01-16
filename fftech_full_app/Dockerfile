# Use official Python 3.13 slim base
FROM python:3.13-slim

# Install all required native libraries for WeasyPrint and Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    libglib2.0-0 gobject-introspection fontconfig libfreetype6 libharfbuzz0b \
    libjpeg62-turbo libpng16-16 zlib1g libxml2 libxslt1.1 shared-mime-info \
    libffi-dev libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
    libxrandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install --with-deps chromium

# Copy application
COPY . .

# ✅ CORRECT START COMMAND (NO $PORT, NO UVICORN CLI)
CMD ["python", "-m", "app.main"]
