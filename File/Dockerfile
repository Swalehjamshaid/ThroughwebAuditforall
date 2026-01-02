
# Use latest stable Python (small footprint)
FROM python:3.12-slim

# Prevent interactive prompts & improve Python behavior
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Work directory inside container
WORKDIR /app

# Copy app source (Dockerfile is in File/, so copy the contents of File/)
COPY . ./

# Install dependencies
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# Local default; Railway injects PORT at runtime
ENV PORT=8000

# IMPORTANT: Shell-wrapped CMD so ${PORT} expands before Gunicorn starts
# Change 'app.main:app' to match your actual module:variable (e.g., 'main:app' if your app is in main.py at root)
CMD ["/bin/sh", "-c", "exec gunicorn app.main:app -b 0.0.0.0:${PORT} -w 2 --threads 4 --timeout 120"]
