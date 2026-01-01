
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["/bin/sh", "-c", "exec gunicorn app.main:app -b 0.0.0.0:${PORT:-8000} -w 2"]
