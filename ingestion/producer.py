"""
Kafka producer for the data ingestion layer.

Replay mode publishes the historical daily readings for the three catchments
(CHIRPS, IMERG and ERA5-Land values), one message per catchment per day in date
order, on the hydro-raw-readings topic. Live mode, fetching the same values from
Google Earth Engine, will replace read_rows(). Flood labels are not sent, since a
live feed has none.

Usage (from the ingestion/ directory, with the Kafka container running):
    python producer.py [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--catchment NAME]
                       [--interval SECONDS] [--dry-run]
"""

import argparse
import csv
import json
import time

from confluent_kafka import Producer

import config


def read_rows(catchment=None, start=None, end=None):
    """Yield the replay file's rows in date order, optionally one catchment and a date range."""
    with open(config.SIMULATION_DATA_FILE, newline="") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: (r["date"], r["catchment"]))
    for row in rows:
        if catchment and config.CATCHMENT_NAMES[row["catchment"]] != catchment:
            continue
        if (start and row["date"] < start) or (end and row["date"] > end):
            continue
        yield row


def to_message(row):
    return {
        "date": row["date"],
        "catchment": config.CATCHMENT_NAMES[row["catchment"]],
        "source": config.REPLAY_SOURCE,
        "readings": {field: float(row[field]) for field in config.FEATURE_FIELDS},
    }


def delivery_report(err, msg):
    if err is not None:
        print(f"delivery failed for key {msg.key()}: {err}")


def main():
    parser = argparse.ArgumentParser(description="Replay the historical daily readings through Kafka.")
    parser.add_argument("--start", help="First date to send, YYYY-MM-DD (default: start of the file).")
    parser.add_argument("--end", help="Last date to send, YYYY-MM-DD (default: end of the file).")
    parser.add_argument("--catchment", help="Send one catchment only, by its database name.")
    parser.add_argument("--interval", type=float, default=0.5, help="Seconds between messages (default 0.5).")
    parser.add_argument("--dry-run", action="store_true", help="Print the first messages instead of sending.")
    args = parser.parse_args()

    rows = read_rows(args.catchment, args.start, args.end)
    if args.dry_run:
        messages = [to_message(r) for r in rows]
        for m in messages[:3]:
            print(json.dumps(m, indent=2))
        print(f"dry run: {len(messages)} messages would be sent to '{config.TOPIC_RAW_READINGS}'.")
        return

    producer = Producer({"bootstrap.servers": config.KAFKA_BROKER})
    count = 0
    for row in rows:
        message = to_message(row)
        producer.produce(
            config.TOPIC_RAW_READINGS,
            key=message["catchment"].encode("utf-8"),
            value=json.dumps(message).encode("utf-8"),
            callback=delivery_report,
        )
        producer.poll(0)  # trigger delivery callbacks without blocking
        count += 1
        if count % 100 == 0:
            print(f"published {count} readings...")
        time.sleep(args.interval)

    producer.flush()
    print(f"done: published {count} readings to '{config.TOPIC_RAW_READINGS}'.")


if __name__ == "__main__":
    main()