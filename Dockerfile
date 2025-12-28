
# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Install deps
COPY fftech_audit/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy source + script
COPY . .
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 8080

# Run via the script (guarantees $PORT is expanded)
CMD ["./start.sh"]
