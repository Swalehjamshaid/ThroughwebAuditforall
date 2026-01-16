vFROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
EXPOSE 8000

# UPDATED LINE: No brackets, no quotes around $PORT
CMD uvicorn backend.main:app --host 0.0.0.0 --port $PORT
