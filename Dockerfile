
# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Install dependencies
COPY fftech_audit/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy source + start script
COPY . .
COPY start.sh .
RUN chmod +x start.sh

# Optional: ensure Python can resolve packages from /app
# ENV PYTHONPATH=/app

EXPOSE 8080

# Run via script (guarantees $PORT expansion)
CMD ["./start.sh"]
