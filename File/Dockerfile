
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1
WORKDIR /app

# Install dependencies first
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app/

# Normalize CRLF line endings and ensure scripts are executable
RUN sed -i 's/$//' /app/start.sh && chmod +x /app/start.sh

EXPOSE 8080

# Run via bash to avoid shebang/format issues
CMD ["bash", "/app/start.sh"]
