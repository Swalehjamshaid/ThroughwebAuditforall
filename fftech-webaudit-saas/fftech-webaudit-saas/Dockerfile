# Final single image serving FastAPI and static frontend
FROM python:3.11-slim

# System deps for psycopg2 and reportlab fonts
RUN apt-get update && apt-get install -y --no-install-recommends     build-essential     libpq-dev     && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install backend deps
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy backend
COPY backend /app/backend

# Copy built frontend (Railpack step will place frontend/dist here)
COPY frontend/dist /app/frontend/dist

ENV PORT=8000
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
