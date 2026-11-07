import json
import urllib.error
import urllib.request

from confluent_kafka import Consumer

import config
import db
from validation import check_reading

DB_COLUMN = {"rain_mm": "rainfall_mm"}  # message field -> hydro_data_records column


def get_catchment_ids():
    """{catchment name: id} for the active catchments only."""
    return {r["name"]: r["id"] for r in db.query_all("SELECT id, name FROM catchment_areas WHERE is_active")}


def get_source_id(name):
    """The data source's id, adding it the first time a new source appears."""
    row = db.query_one("SELECT id FROM data_sources WHERE name = %s", (name,))
    if row is None:
        db.execute("INSERT INTO data_sources (name, source_type, fetch_interval, datasets) "
                   "VALUES (%s, 'daily-feed', '1 day', 'CHIRPS, IMERG, ERA5-Land')",
                   (name,))
        row = db.query_one("SELECT id FROM data_sources WHERE name = %s", (name,))
    db.execute("UPDATE data_sources SET connection_status = 'connected' WHERE id = %s", (row["id"],))
    return row["id"]


def is_duplicate(source_id, catchment_id, day):
    return db.query_one(
        "SELECT 1 FROM hydro_data_records WHERE data_source_id = %s AND catchment_id = %s AND recorded_at = %s",
        (source_id, catchment_id, day)) is not None


def save_reading(source_id, catchment_id, message):
    cols = [DB_COLUMN.get(f, f) for f in config.FEATURE_FIELDS]
    values = [message["readings"][f] for f in config.FEATURE_FIELDS]
    return db.execute_returning(
        f"INSERT INTO hydro_data_records (recorded_at, data_source_id, catchment_id, {', '.join(cols)}) "
        f"VALUES (%s, %s, %s, {', '.join(['%s'] * len(cols))}) RETURNING id",
        (message["date"], source_id, catchment_id, *values))


def reject(message, reason):
    detail = f"{message.get('catchment')} {message.get('date')}: {reason}"
    print(f"rejected {detail}")
    db.execute("INSERT INTO system_logs (actor, action, detail, category) "
               "VALUES ('consumer', 'reading_rejected', %s, 'pipeline')", (detail,))


def request_detection(catchment_id, day, record_id):
    """Ask the backend to score this catchment-day, and return its reply."""
    body = json.dumps({"catchment_id": catchment_id, "date": day, "hydro_data_record_id": record_id}).encode()
    req = urllib.request.Request(config.DETECTION_URL, data=body, method="POST", headers={
        "Content-Type": "application/json", "X-Internal-Token": config.INTERNAL_API_TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:  # e.g. 422 when fewer than 14 days are stored so far
        return json.loads(e.read() or b"{}")
    except urllib.error.URLError as e:
        return {"scored": False, "reason": f"backend not reachable ({e.reason})"}


def handle(message, catchment_ids, source_ids, counts):
    """Check, save and score one reading."""
    if "readings" not in message:  # old message format from before the final features
        counts["skipped"] += 1
        return
    catchment_id = catchment_ids.get(message.get("catchment"))
    reason = check_reading(message, config.FEATURE_FIELDS)
    if reason is None and catchment_id is None:
        reason = "unknown or inactive catchment"
    if reason is None and not message.get("source"):
        reason = "no source named"
    if reason is None:
        source = message["source"]
        if source not in source_ids:
            source_ids[source] = get_source_id(source)
        if is_duplicate(source_ids[source], catchment_id, message["date"]):
            reason = "already stored for this source, catchment and date"
    if reason:
        reject(message, reason)
        counts["rejected"] += 1
        return
    record_id = save_reading(source_ids[message["source"]], catchment_id, message)
    counts["saved"] += 1
    result = request_detection(catchment_id, message["date"], record_id)
    if result.get("scored"):
        counts["scored"] += 1
        counts["flagged"] += int(result["flagged"])
    elif "not reachable" in result.get("reason", ""):
        print(result["reason"])


def main():
    catchment_ids = get_catchment_ids()
    source_ids = {}
    counts = {"saved": 0, "rejected": 0, "skipped": 0, "scored": 0, "flagged": 0}
    consumer = Consumer({
        "bootstrap.servers": config.KAFKA_BROKER,
        "group.id": config.CONSUMER_GROUP,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,  # commit only after a reading is handled
    })
    consumer.subscribe([config.TOPIC_RAW_READINGS])
    print(f"listening on '{config.TOPIC_RAW_READINGS}' (Ctrl+C to stop)...")
    try:
        while True:
            record = consumer.poll(1.0)
            if record is None:
                continue
            if record.error():
                print(f"consumer error: {record.error()}")
                continue
            handle(json.loads(record.value()), catchment_ids, source_ids, counts)
            consumer.commit(message=record, asynchronous=False)
            if counts["saved"] and counts["saved"] % 100 == 0:
                print(counts)
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()
        print("stopped:", counts)


if __name__ == "__main__":
    main()