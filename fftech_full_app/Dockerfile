FROM python:3.13-slim

# Install WeasyPrint system libraries (correct & complete)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
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
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose port (Railway sets $PORT env var)
EXPOSE $PORT

# Run uvicorn without --port (auto-uses $PORT from env)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0"]
