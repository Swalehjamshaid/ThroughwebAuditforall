
# Use latest stable Python
FROM python:3.12-slim

# Prevent interactive prompts & improve Python output
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /app

# Copy ONLY the contents of the 'File' folder into /app
# (Ensure your requirements.txt lives inside File/)
COPY File/ ./

# Install dependencies
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# Railway injects PORT; keep a local default for dev
ENV PORT=8000

# Start Gunicorn (shell-wrapped so ${PORT} expands)
# IMPORTANT: Replace 'main:app' with your actual module:variable (e.g., app.main:app)
CMD ["/bin/sh", "-c", "exec gunicorn app.main:app -b 0.0.0.0:${PORT} -w 2 --threads 4 --timeout 120"]
