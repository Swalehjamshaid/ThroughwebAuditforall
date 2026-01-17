# Official Python 3.13 slim base (Debian-based, perfect for Railway)
FROM python:3.13-slim

# Install all required system libraries for WeasyPrint (fixes gobject, cairo, pango errors)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    gobject-introspection \
    fontconfig \
    libfreetype6 \
    libharfbuzz0b \
    libjpeg62-turbo \
    libpng16-16 \
    zlib1g \
    libxml2 \
    libxslt1.1 \
    shared-mime-info \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set working directory (standard for Railway)
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Expose the port (Railway assigns $PORT automatically)
EXPOSE $PORT

# Run uvicorn WITHOUT --port flag → it auto-reads $PORT from environment
# This fixes the "Invalid value for '--port': '$PORT'" error
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0"]
