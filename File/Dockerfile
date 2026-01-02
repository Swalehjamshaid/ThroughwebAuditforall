
# Base image
FROM python:3.11-slim

# Workdir
WORKDIR /app

# ---- Dependencies (layer caching) ----
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ---- Copy source last ----
COPY . .

# ---- Runtime configuration ----
# Railway injects PORT at runtime; keep a sensible default
ENV PORT=8000

# Inject Google PageSpeed Insights API key at build time (fallback to hard-coded here)
# NOTE: Prefer setting at runtime with: docker run -e GOOGLE_PSI_API_KEY=...
ENV GOOGLE_PSI_API_KEY="AIzaSyDUVptDEm1ZbiBdb5m1DGjvKCW_LBVJMEw"

# ---- Start Gunicorn ----
# Shell-wrapped CMD so ${PORT} expands before Gunicorn starts
CMD ["/bin/sh", "-c", "exec gunicorn app.main:app -b 0.0.0.0:${PORT} -w 2"]
``
