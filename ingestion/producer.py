"""
Kafka producer simulating the data ingestion layer (proposal 3.5.2/3.6.3).

Reads the historical labelled dataset and republishes each row, in
chronological order, as a JSON message on the hydro-raw-readings topic, at
a configurable interval, to simulate a live multi-source feed (CHIRPS,
GloFAS, KMD) arriving in real time. This lets the rest of the pipeline be
built and tested end to end before a true live source is wired in: once
one is available, only read_rows() below needs to change.

Usage (from the ingestion/ directory, with the Kafka container running):
    python producer.py [--interval SECONDS] [--catchment NAME]
"""

import argparse
import csv
import json
import time

from kafka import KafkaProducer

import config


def read_rows(catchment=None):
    """Yield dataset rows in chronological order, across catchments.

    This is the one function to replace with a real call to CHIRPS,
    GloFAS, or KMD when a live source is wired in; everything downstream
    of it (the message format, the topic, the consumer) stays the same.
    """
    with open(config.SIMULATION_DATA_FILE, newline="") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: (r["date"], r["catchment"]))
    for row in rows:
        if catchment and row["catchment"] != catchment:
            continue
        yield row


def to_message(row):
    return {
        "record_id": int(row["record_id"]),
        "date": row["date"],
        "catchment": row["catchment"],
        "features": {field: float(row[field]) for field in config.FEATURE_FIELDS},
        "flood_event": int(row["flood_event"]),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Simulate the hydrometeorological ingestion feed from the historical dataset."
    )
    parser.add_argument(
        "--interval", type=float, default=0.5,
        help="Seconds to wait between messages (default 0.5).",
    )
    parser.add_argument(
        "--catchment", default=None,
        help="Restrict the feed to a single catchment (default: all six).",
    )
    args = parser.parse_args()

    producer = KafkaProducer(
        bootstrap_servers=config.KAFKA_BROKER,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8"),
    )

    count = 0
    try:
        for row in read_rows(args.catchment):
            message = to_message(row)
            producer.send(config.TOPIC_RAW_READINGS, key=message["catchment"], value=message)
            count += 1
            if count % 100 == 0:
                print(f"published {count} readings...")
            time.sleep(args.interval)
    finally:
        producer.flush()

    print(f"done: published {count} readings to '{config.TOPIC_RAW_READINGS}'.")


if __name__ == "__main__":
    main()
