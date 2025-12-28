
# Dockerfile — explicit container build for FF Tech AI Website Audit SaaS
# Uses Python 3.11 slim base (Debian). If you need Alpine, switch to python:3.11-alpine and install build deps for psycopg2.

FROM python:3.11-slim

# Prevent Python from writing .pyc and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Default port (Railway will inject PORT)
ENV PORT=8080

# Work directory
WORKDIR /app

# System deps (optional; uncomment if you need fonts, curl for debugging)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     curl \
#     && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your app
COPY . .

# Expose port (informational)
EXPOSE 8080

# Start FastAPI app (Railway sets $PORT)
CMD ["sh", "-c", "uvicorn fftech_audit.app:app --host 0.0.0.0 --port ${PORT}"]
