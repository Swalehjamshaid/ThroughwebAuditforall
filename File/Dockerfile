
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app

RUN apt-get update -y && apt-get install -y --no-install-recommends \
    build-essential tzdata sqlite3 curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app
COPY run.py ./run.py   # ✅ This line copies the new run.py file

ENV PORT=8000
EXPOSE 8000

# Recommended CMD (Gunicorn for production robustness)
CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:${PORT:-8000} app.main:app"]

# If Railway overrides with python /app/run.py, the file now exists and works.
