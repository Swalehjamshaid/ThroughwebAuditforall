
# File/Dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first to leverage Docker layer caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the whole project
COPY . /app/

# --- FIX: normalize line endings + make scripts executable ---
# If start.sh was committed with Windows CRLF, remove carriage returns (\r)
RUN sed -i 's/\r$//' /app/start.sh && \
    chmod +x /app/start.sh

EXPOSE 8000

# --- FIX: invoke script via bash to avoid shebang / format issues ---
CMD ["bash", "/app/start.sh"]
