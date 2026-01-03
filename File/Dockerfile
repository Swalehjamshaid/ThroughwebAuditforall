
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app/
RUN sed -i 's/$//' /app/start.sh && chmod +x /app/start.sh
EXPOSE 8080
CMD ["bash", "/app/start.sh"]
