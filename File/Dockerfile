
# File/Dockerfile  (build context is the File/ folder)
FROM python:3.12-slim

# Prevent interactive tz prompts in slim images
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 👇 These files MUST exist at File/requirements.txt and File/constraints.txt
COPY requirements.txt constraints.txt ./
RUN python -m pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt -c constraints.txt

# Copy the application (everything under File/) into the image
COPY . .

# Railway injects a numeric PORT; shell-wrapper ensures ${PORT} expands
ENV PORT=8000
CMD ["/bin/sh", "-c", "exec gunicorn app.main:app -b 0.0.0.0:${PORT} -w 2 --timeout 45 --preload"]
