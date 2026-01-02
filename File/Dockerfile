
# Base image
FROM python:3.11-slim

# Ensure non-interactive apt (if you add packages later)
ENV DEBIAN_FRONTEND=noninteractive

# Workdir
WORKDIR /app

# Install Python deps first for better layer caching
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source last
COPY . .

# Runtime config: Railway injects PORT; keep a default for local runs
ENV PORT=8000

# If you need the PSI key baked into the image (you asked for this earlier):
# NOTE: Prefer -e GOOGLE_PSI_API_KEY at runtime for security.
ENV GOOGLE_PSI_API_KEY="AIzaSyDUVptDEm1ZbiBdb5m1DGjvKCW_LBVJMEw"

# Start Gunicorn; shell-wrapped so ${PORT} expands
CMD ["/bin/sh", "-c", "exec gunicorn app.main:app -b 0.0.0.0:${PORT} -w 2"]
