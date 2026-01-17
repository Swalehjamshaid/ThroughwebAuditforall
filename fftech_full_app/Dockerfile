# Official Python 3.13 slim base image
FROM python:3.13-slim

# Install system dependencies for WeasyPrint (critical for PDF generation)
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

# Set working directory
WORKDIR /app

# Copy requirements first (better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application
COPY . .

# Expose the port Railway will assign via $PORT
EXPOSE $PORT

# Run uvicorn without explicit --port (automatically uses $PORT from env)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0"]
