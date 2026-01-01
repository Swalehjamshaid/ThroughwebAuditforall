
FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PORT=8000  # local default

# Shell-wrapped CMD ensures ${PORT} expands at runtime
CMD ["/bin/sh", "-c", "exec gunicorn app.main:app -b 0.0.0.0:${PORT} -w 2"]
``
