"""
Kafka consumer implementing the stream processing layer (proposal
3.5.6/3.6.3): "align incoming data ... to a common time interval,
normalise numerical values, evaluate threshold conditions, and trigger
preliminary alerts where defined risk levels are exceeded."

For each incoming reading, this consumer:
  1. persists the raw observation to hydro_data_records (the storage
     layer, already in place on feat/database-schema),
  2. evaluates simple, rule-based threshold conditions and writes a
     preliminary alert to the alerts table when one is exceeded.

This is deliberately separate from, and simpler than, the LSTM-based
anomaly detection module (proposal 3.6.4): that is a heavier, model-driven
step that reads sequences back out of hydro_data_records on its own
schedule, rather than running inline on every message here. Preliminary,
rule-based alerts give a fast first signal while that heavier scoring
catches up.

Usage (from the ingestion/ directory, with the Kafka and db containers
running, and after db/seed.py has been run at least once):
    python consumer.py
"""

import json

from confluent_kafka import Consumer

import config
import db

SOURCE_NAME = "simulated-dataset-feed"


def get_source_id():
    row = db.query_one("SELECT id FROM data_sources WHERE name = %s", (SOURCE_NAME,))
    if row is None:
        raise RuntimeError(
            f"data source '{SOURCE_NAME}' not found. Run db/seed.py first."
        )
    return row["id"]


def get_catchment_ids():
    """Return {catchment name: id} for every seeded catchment."""
    rows = db.query_all("SELECT id, name FROM catchment_areas")
    if not rows:
        raise RuntimeError("no catchment_areas found. Run db/seed.py first.")
    return {row["name"]: row["id"] for row in rows}


def persist_reading(data_source_id, catchment_id, message):
    features = message["features"]
    db.execute(
        "INSERT INTO hydro_data_records "
        "(recorded_at, data_source_id, catchment_id, rainfall_mm, "
        " river_discharge_m3s, soil_moisture_m3m3, evaporation_mm, oni) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            message["date"],
            data_source_id,
            catchment_id,
            features["rainfall_mm"],
            features["river_discharge_m3s"],
            features["soil_moisture_m3m3"],
            features["evaporation_mm"],
            features["oni"],
        ),
    )


def evaluate_preliminary_risk(message):
    """Rule-based check, independent of the LSTM model. Returns a
    severity string ('high'/'medium') or None if nothing is exceeded."""
    features = message["features"]
    rainfall_exceeded = features["rainfall_mm"] > config.RAINFALL_ALERT_MM
    discharge_exceeded = features["discharge_change"] > config.DISCHARGE_CHANGE_ALERT

    if rainfall_exceeded and discharge_exceeded:
        return "high"
    if rainfall_exceeded or discharge_exceeded:
        return "medium"
    return None


def raise_alert(catchment_id, severity):
    db.execute(
        "INSERT INTO alerts (catchment_id, severity, status) VALUES (%s, %s, %s)",
        (catchment_id, severity, "active"),
    )


def mark_source_connected(data_source_id):
    db.execute(
        "UPDATE data_sources SET connection_status = 'connected' WHERE id = %s",
        (data_source_id,),
    )


def main():
    data_source_id = get_source_id()
    catchment_ids = get_catchment_ids()
    mark_source_connected(data_source_id)

    consumer = Consumer({
        "bootstrap.servers": config.KAFKA_BROKER,
        "group.id": config.CONSUMER_GROUP,
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([config.TOPIC_RAW_READINGS])

    print(f"listening on '{config.TOPIC_RAW_READINGS}' (Ctrl+C to stop)...")
    processed = 0
    alerts_raised = 0
    try:
        while True:
            record = consumer.poll(1.0)
            if record is None:
                continue
            if record.error():
                print(f"consumer error: {record.error()}")
                continue

            message = json.loads(record.value().decode("utf-8"))
            catchment_id = catchment_ids.get(message["catchment"])
            if catchment_id is None:
                print(f"skipping unknown catchment '{message['catchment']}'.")
                continue

            persist_reading(data_source_id, catchment_id, message)

            severity = evaluate_preliminary_risk(message)
            if severity is not None:
                raise_alert(catchment_id, severity)
                alerts_raised += 1

            processed += 1
            if processed % 100 == 0:
                print(f"processed {processed} readings, raised {alerts_raised} preliminary alerts so far...")
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()
        print(f"stopped: processed {processed} readings, raised {alerts_raised} preliminary alerts in total.")


if __name__ == "__main__":
    main()
