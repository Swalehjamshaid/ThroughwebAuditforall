
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app

# Install minimal OS packages required by Python / SQLite / health tools
RUN apt-get update -y && apt-get install -y --no-install-recommends     build-essential tzdata sqlite3 curl  && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# App code
COPY app ./app

# Copy entrypoint from app/ into container root (/app/run.py) to match Railway command
COPY app/run.py ./run.py

ENV PORT=8000
EXPOSE 8000

# Robust default (Railway may still use startCommand from railway.json)
CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:${PORT:-8000} app.main:app"]
