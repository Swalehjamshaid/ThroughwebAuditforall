
# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Install dependencies (your requirements are inside the folder)
COPY fftech_audit/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy source + the start script
COPY . .
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 8080

# Use the script so $PORT is properly read & passed as an integer
CMD ["./start.sh"]
