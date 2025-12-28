
# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Install Python dependencies (requirements.txt lives inside fftech_audit/)
COPY fftech_audit/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ✅ Copy entire project: templates, static, app code
COPY . .

# Start script
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 8080

CMD ["./start.sh"]
