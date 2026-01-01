FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# We hardcode 8000 here and in the CMD to prevent expansion errors
ENV PORT=8000

# Using the number directly is the most stable way to fix this error
CMD gunicorn app.main:app -b 0.0.0.0:8000 -w 2
