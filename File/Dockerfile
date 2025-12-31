
# Dockerfile (repo root)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app

RUN apt-get update -y && apt-get install -y --no-install-recommends \
    build-essential tzdata sqlite3 curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the whole app folder including templates, static, and your run.py
COPY app ./app

# ✅ Your run.py lives inside app/, so copy it from there into container root /app
COPY app/run.py ./run.py

ENV PORT=8000
EXPOSE 8000

# Robust default CMD; Railway can still override to `python /app/run.py`
CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:${PORT:-8000} app.main:app"]
