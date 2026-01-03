
FROM python:3.12-slim
ENV DEBIAN_FRONTEND=noninteractive     PYTHONUNBUFFERED=1     PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt constraints.txt ./
RUN python -m pip install --upgrade pip &&     pip install --no-cache-dir -r requirements.txt -c constraints.txt
COPY . .
ENV PORT=8000
CMD ["/bin/sh", "-c", "exec gunicorn app.main:app -b 0.0.0.0:${PORT} -w 2 --timeout 45 --preload"]
