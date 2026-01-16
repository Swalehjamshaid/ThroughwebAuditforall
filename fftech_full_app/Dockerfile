FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Copy requirements for caching
COPY requirements.txt .

# Install system dependencies needed for your packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    # For graphical / reportlab / matplotlib / Pillow
    libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    libglib2.0-0 gobject-introspection fontconfig libfreetype6 libharfbuzz0b \
    libjpeg62-turbo libpng16-16 zlib1g libxml2 libxslt1.1 shared-mime-info \
    libffi-dev libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
    libxrandr2 libgbm1 libasound2 \
    # Build dependencies for psycopg2
    libpq-dev gcc python3-dev \
    && pip install --no-cache-dir -r requirements.txt \
    # Clean up unnecessary build dependencies to reduce image size
    && apt-get purge -y --auto-remove gcc python3-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the rest of the app
COPY . .

# Command to run your app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
