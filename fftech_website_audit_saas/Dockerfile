# Use official Python 3.13 slim base (matches your env)
FROM python:3.13-slim

# Install ALL required system libraries for WeasyPrint (this fixes gobject-2.0-0 error)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core WeasyPrint libs
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    # GObject & GLib (fixes the exact error)
    libglib2.0-0 \
    libgobject2.0-0 \
    gobject-introspection \
    # Fonts & text rendering
    fontconfig \
    freetype2-demos \
    libfontconfig1 \
    libharfbuzz0b \
    # Images & PNG/JPEG
    libjpeg62-turbo \
    libpng16-16 \
    zlib1g \
    # XML & utils
    libxml2 \
    libxslt1.1 \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set working directory
WORKDIR /app

# Copy & install Python dependencies first (caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your app
COPY . .

# Expose port (Railway uses $PORT)
EXPOSE $PORT

# Run the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$PORT"]
