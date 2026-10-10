# Ingestion and stream processing

Simulates the Kafka data ingestion layer and the stream processing layer
(proposal sections 3.5.2, 3.5.6, 3.6.3) using the historical labelled
dataset as a stand-in for the real CHIRPS/GloFAS/KMD feeds, so the rest of
the pipeline can be built and tested end to end before those live sources
are wired in.

## Running it

1. Start the database and Kafka broker (from the `db/` directory):
   ```
   docker compose up -d
   ```
2. Install dependencies (from this directory, ideally in a virtualenv):
   ```
   pip install -r requirements.txt
   pip install -r ../backend/requirements.txt
   ```
3. Seed the catchments and data sources, once (from the `db/` directory):
   ```
   python seed.py
   ```
4. In one terminal, start the consumer (the stream processor):
   ```
   python consumer.py
   ```
5. In another terminal, start the producer (the simulated feed):
   ```
   python producer.py --interval 0.1
   ```

Watch the consumer's terminal for progress, then check the database:
```
docker compose exec db psql -U flood_pipeline -d flood_pipeline \
  -c "SELECT count(*) FROM hydro_data_records;" \
  -c "SELECT severity, count(*) FROM alerts GROUP BY severity;"
```

## Notes

- `producer.py`'s `read_rows()` is the one function to replace with a real
  CHIRPS/GloFAS/KMD call once a live source is available; the message
  format, topic and consumer stay the same.
- `db/seed.py`'s catchment coordinates are rough placeholders, not the
  values used in the ERA5/CHIRPS extraction notebooks (see
  project-checklist.md). Replace them once the real values are found.
- The consumer's threshold checks are simple and rule-based, separate from
  the LSTM anomaly detection module, which is its own, heavier milestone.
