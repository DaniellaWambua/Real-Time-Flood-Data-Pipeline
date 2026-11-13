# One image for the Flask backend, the Kafka consumer and the Earth Engine producer.
# Built on the server: docker compose -f deploy/docker-compose.prod.yml build
FROM python:3.9-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY deploy/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend/ /app/backend/
COPY ingestion/ /app/ingestion/
COPY models/ /app/models/
COPY data_collection/data/05_spatial/processed/catchments.geojson /app/data_collection/data/05_spatial/processed/catchments.geojson
# The secrets come from the environment (deploy/.env), never from a file baked into the image
RUN rm -f /app/backend/.env
WORKDIR /app/backend
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "1", "--threads", "4", "--timeout", "120", "app:app"]
