# Use latest stable Python
FROM python:3.12-slim

# Prevent interactive prompts & improve Python output
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /app

# Copy ONLY the contents of the 'File' folder into /app
COPY File/ .

# Install dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# Expose port (Railway uses $PORT)
ENV PORT=8000

# Start Gunicorn
# CHANGE "main:app" to match your actual file and app variable
# Examples:
#   main:app      → if your file is main.py and app = Flask(__name__)
#   app:app       → if your file is app.py
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "--workers", "2", "--threads", "4", "--timeout", "120", "main:app"]
