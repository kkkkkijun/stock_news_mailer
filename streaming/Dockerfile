FROM python:3.12-slim

WORKDIR /app

COPY streaming/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY streaming/ /app/streaming/

CMD ["python", "-u", "streaming/consumer.py"]
