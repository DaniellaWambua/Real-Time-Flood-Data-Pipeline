# One image for the Flask backend, the Kafka consumer and the Earth Engine producer.
# Built on the server: docker compose -f deploy/docker-compose.prod.yml build
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY deploy/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend/ /app/backend/
COPY ingestion/ /app/ingestion/
COPY models/ /app/models/
COPY data_collection/data/05_spatial/processed/catchments.geojson /app/data_collection/data/05_spatial/processed/catchments.geojson
# The secrets come from the environment (deploy/.env), never from a file baked into the image.
# The copied code and model files keep the permissions they had on the server, which can be owner-only,
# so they are made readable (and folders enterable) for the unprivileged user below.
RUN rm -f /app/backend/.env && chmod -R a+rX /app
# Run as an ordinary user, not root, so a flaw in the app cannot change the image or the system inside it.
# UID 1000 matches azureuser on the VM, so the read-only secrets mounted from deploy/secrets stay readable.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin app
USER app
WORKDIR /app/backend
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "1", "--threads", "4", "--timeout", "120", "app:app"]
