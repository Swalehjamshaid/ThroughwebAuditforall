FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your app code
COPY . .

# EXPOSE is optional on Railway but good for documentation
EXPOSE 8000

# FIXED LINE: No brackets, no quotes around $PORT
CMD uvicorn backend.main:app --host 0.0.0.0 --port $PORT
