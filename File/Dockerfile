
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app

# Install minimal system packages required by Python and SQLite fallback
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    build-essential tzdata sqlite3 curl \
 && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt ./ 
RUN pip install --upgrade pip && pip install -r requirements.txt

# Your application code
COPY app ./app

# *** NEW: copy the run.py entrypoint so 'python /app/run.py' works ***
COPY run.py ./run.py

ENV PORT=8000
EXPOSE 8000

# EITHER keep Gunicorn CMD (recommended for production robustness)…
CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:${PORT:-8000} app.main:app"]

# …OR if you prefer to always start with run.py (optional), comment the Gunicorn line above
# and use the following instead:
# CMD ["sh", "-c", "python /app/run.py"]
