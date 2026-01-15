# Use official Python 3.13 slim base (Debian Trixie/Bookworm compatible)
FROM python:3.13-slim

# Install all required native libraries for WeasyPrint (correct package names)
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
    # Image support (JPEG, PNG)
    libjpeg62-turbo \
    libpng16-16 \
    zlib1g \
    # XML & utilities
    libxml2 \
    libxslt1.1 \
    shared-mime-info \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the port (Railway uses $PORT env var)
EXPOSE $PORT

# Run uvicorn without --port → it auto-reads $PORT from environment
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0"]
