FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y curl gnupg ca-certificates     && curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -     && apt-get install -y nodejs     && npm install -g lighthouse     && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app

ENV PORT=8000
EXPOSE 8000
# Replace module:object if your app uses a different entry
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:${PORT}"]
