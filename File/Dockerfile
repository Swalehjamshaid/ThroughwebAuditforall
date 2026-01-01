FROM python:3.11-slim

# Prevent pip from caching and saving space
ENV PIP_NO_CACHE_DIR=1

# Set the working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Set the default port (Cloud providers may override this)
ENV PORT=8000

# FIX: Removed the square brackets to allow Shell expansion of $PORT
CMD gunicorn app.main:app -b 0.0.0.0:$PORT -w 2
