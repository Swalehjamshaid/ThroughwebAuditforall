
FROM python:3.11-slim

# Install Node LTS & Lighthouse CLI (for audits)
RUN apt-get update && apt-get install -y curl gnupg ca-certificates     && curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -     && apt-get install -y nodejs     && npm install -g lighthouse     && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENV PYTHONPATH=/app
ENV PORT=8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "run:app"]
