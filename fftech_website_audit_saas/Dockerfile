FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

# Updated this line to ensure pydantic[email] is installed
RUN pip install --no-cache-dir -r /app/requirements.txt && \
    pip install --no-cache-dir "pydantic[email]"

COPY app /app/app
COPY Procfile /app/Procfile
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
