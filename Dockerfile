
# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Ensure Python writes no .pyc and logs are unbuffered
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Work in /app
WORKDIR /app

# (Optional) System dependencies for common Python wheels (psycopg2, lxml, pillow, etc.)
# Comment out if not needed; uncomment if pip fails due to missing build tools.
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential \
#     gcc \
#     libpq-dev \
#     && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage Docker layer caching
COPY fftech_audit/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the full source
COPY . .

# Expose port
EXPOSE 8080

# Run the app via uvicorn
CMD ["sh", "-c", "uvicorn fftech_audit.app:app --host 0.0.0.0 --port ${PORT}"]
