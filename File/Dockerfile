FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# NO "ENV PORT" here - let Railway provide it
# NO Square brackets - this allows Railway to swap $PORT for a number
CMD gunicorn app.main:app -b 0.0.0.0:$PORT -w 2
