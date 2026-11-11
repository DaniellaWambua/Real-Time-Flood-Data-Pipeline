import json
import math
import urllib.error
from datetime import date
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


def post_internal(url, payload):
    """POST to one of the backend's internal endpoints and return its JSON reply."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST", headers={
        "Content-Type": "application/json", "X-Internal-Token": config.INTERNAL_API_TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:  # e.g. 422 when fewer than 14 days are stored so far
        return json.loads(e.read() or b"{}")
    except urllib.error.URLError as e:
        return {"scored": False, "reason": f"backend not reachable ({e.reason})"}


def request_detection(catchment_id, day, record_id, notify=False):
    """Ask the backend to score this catchment-day, and return its reply. notify asks it to email
    any new alert, which only live readings do."""
    return post_internal(config.DETECTION_URL, {"catchment_id": catchment_id, "date": day,
                                                "hydro_data_record_id": record_id, "notify": notify})


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
    result = request_detection(catchment_id, message["date"], record_id, notify=message["source"] == config.LIVE_SOURCE)
    if result.get("scored"):
        counts["scored"] += 1
        counts["flagged"] += int(result["flagged"])
    elif "not reachable" in result.get("reason", ""):
        print(result["reason"])


def check_forecast(message, catchment_ids):
    """None if the forecast message is usable, otherwise the reason it is rejected."""
    if catchment_ids.get(message.get("catchment")) is None:
        return "unknown or inactive catchment"
    days = message.get("days")
    if not days:
        return "no forecast days"
    for d in days:
        try:
            date.fromisoformat(d.get("date", ""))
        except (TypeError, ValueError):
            return f"date is not YYYY-MM-DD ({d.get('date')})"
        mm = d.get("precipitation_mm")
        if mm is None or isinstance(mm, bool) or not isinstance(mm, (int, float)) or math.isnan(mm) or mm < 0:
            return f"missing or invalid rainfall for {d.get('date')} ({mm})"
    return None


def handle_forecast(message, catchment_ids, counts):
    """Store a catchment's forecast, flag days at or above the warning level, and log new warnings."""
    reason = check_forecast(message, catchment_ids)
    if reason:
        reject({"catchment": message.get("catchment"), "date": "forecast"}, reason)
        counts["rejected"] += 1
        return
    catchment_id = catchment_ids[message["catchment"]]
    for d in message["days"]:
        mm, warning = float(d["precipitation_mm"]), float(d["precipitation_mm"]) >= config.RAIN_WARNING_MM
        before = db.query_one("SELECT is_warning FROM rainfall_forecasts WHERE catchment_id = %s AND forecast_date = %s",
                              (catchment_id, d["date"]))
        db.execute(
            "INSERT INTO rainfall_forecasts (catchment_id, forecast_date, precipitation_mm, threshold_mm, is_warning, "
            "source, issued_at) VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (catchment_id, forecast_date) DO UPDATE "
            "SET precipitation_mm = EXCLUDED.precipitation_mm, threshold_mm = EXCLUDED.threshold_mm, "
            "is_warning = EXCLUDED.is_warning, source = EXCLUDED.source, issued_at = EXCLUDED.issued_at",
            (catchment_id, d["date"], mm, config.RAIN_WARNING_MM, warning, message.get("source"), message["issued_at"]))
        counts["forecasts"] += 1
        if warning and not (before and before["is_warning"]):  # log each warning once, when first raised
            counts["warnings"] += 1
            db.execute("INSERT INTO system_logs (actor, action, detail, category) "
                       "VALUES ('consumer', 'rainfall_warning', %s, 'alerts')",
                       (f"{message['catchment']}: {mm:.1f} mm forecast for {d['date']} "
                        f"(warning at {config.RAIN_WARNING_MM:.0f} mm)",))
            reply = post_internal(config.WARNING_NOTIFY_URL, {"catchment_id": catchment_id, "date": d["date"],
                                                              "precipitation_mm": mm,
                                                              "threshold_mm": config.RAIN_WARNING_MM})
            if "not reachable" in reply.get("reason", ""):
                print(reply["reason"])


def main():
    catchment_ids = get_catchment_ids()
    source_ids = {}
    counts = {"saved": 0, "rejected": 0, "skipped": 0, "scored": 0, "flagged": 0, "forecasts": 0, "warnings": 0}
    consumer = Consumer({
        "bootstrap.servers": config.KAFKA_BROKER,
        "group.id": config.CONSUMER_GROUP,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,  # commit only after a reading is handled
        "allow.auto.create.topics": True,  # the forecast topic exists once the first forecast is sent
    })
    consumer.subscribe([config.TOPIC_RAW_READINGS, config.TOPIC_FORECASTS])
    print(f"listening on '{config.TOPIC_RAW_READINGS}' and '{config.TOPIC_FORECASTS}' (Ctrl+C to stop)...")
    try:
        while True:
            record = consumer.poll(1.0)
            if record is None:
                continue
            if record.error():
                print(f"consumer error: {record.error()}")
                continue
            if record.topic() == config.TOPIC_FORECASTS:
                handle_forecast(json.loads(record.value()), catchment_ids, counts)
            else:
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