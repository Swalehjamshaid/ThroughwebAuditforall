FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your app code
COPY . .

# FIXED LINE: No brackets, no quotes. 
# This allows the shell to turn $PORT into a number.
CMD uvicorn backend.main:app --host 0.0.0.0 --port $PORT
