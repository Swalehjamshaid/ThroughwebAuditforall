FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libffi-dev
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "run.py"]
