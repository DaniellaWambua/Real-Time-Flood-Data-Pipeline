"""
Kafka producer for the data ingestion layer.

Live mode (--live) fetches each new day's CHIRPS, IMERG and ERA5-Land readings
for the three catchments from Google Earth Engine, up to the last day all three
have published, and records whether the fetch worked on the data source and in
the activity log. Days that IMERG and ERA5-Land have published but CHIRPS has not
(CHIRPS runs about six weeks late) are also sent, without rain_mm and marked
provisional, so the fast model can score them about a week after they happen.
Run it once a day.

Forecast mode (--forecast) fetches the next three days' rainfall forecast for each
catchment from Open-Meteo and publishes it on the hydro-forecasts topic, where the
consumer applies the rainfall warning rule. Run it once a day, or more often.

Replay mode (the default) publishes the historical daily readings from the
model-ready file instead, for testing and demonstrations.

Both send one message per catchment per day, in date order, on the
hydro-raw-readings topic. Flood labels are never sent.

Usage (from the ingestion/ directory, with the Kafka container running):
    python producer.py --live [--interval SECONDS] [--dry-run]
    python producer.py --forecast [--dry-run]
    python producer.py [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--catchment NAME]
                       [--interval SECONDS] [--dry-run]
"""

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timedelta, timezone

from confluent_kafka import Producer

import config
import db
import earth_engine
import forecast


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


def to_live_message(row, provisional=False):
    readings = dict(row["readings"])
    if provisional:
        readings.pop("rain_mm", None)
    return {
        "date": row["date"],
        "catchment": config.CATCHMENT_NAMES[row["catchment"]],
        "source": config.PROVISIONAL_SOURCE if provisional else config.LIVE_SOURCE,
        "readings": readings,
    }


def delivery_report(err, msg):
    if err is not None:
        print(f"delivery failed for key {msg.key()}: {err}")


def publish(messages, interval, topic=config.TOPIC_RAW_READINGS):
    """Send the messages on a topic (the raw readings one by default) and return how many were sent."""
    producer = Producer({"bootstrap.servers": config.KAFKA_BROKER})
    count = 0
    for message in messages:
        producer.produce(
            topic,
            key=message["catchment"].encode("utf-8"),
            value=json.dumps(message).encode("utf-8"),
            callback=delivery_report,
        )
        producer.poll(0)  # trigger delivery callbacks without blocking
        count += 1
        if count % 100 == 0:
            print(f"published {count} readings...")
        time.sleep(interval)
    producer.flush()
    return count


def with_retries(task, attempts=3, wait=30):
    """Run task, retrying after a pause when Earth Engine or the network fails."""
    for attempt in range(1, attempts + 1):
        try:
            return task()
        except ImportError:  # a missing package will not fix itself, so fail at once
            raise
        except Exception as e:  # noqa: BLE001 - any other failure is retried, then reported
            if attempt == attempts:
                raise
            print(f"attempt {attempt} failed ({e}); retrying in {wait * attempt} s")
            time.sleep(wait * attempt)


def last_live_day(source=config.LIVE_SOURCE):
    """The newest day already stored from a live source, or None before the first run."""
    row = db.query_one(
        "SELECT max(r.recorded_at)::date AS day FROM hydro_data_records r "
        "JOIN data_sources s ON s.id = r.data_source_id WHERE s.name = %s", (source,))
    return row["day"] if row else None


def record_status(ok, detail, source=config.LIVE_SOURCE, datasets=config.LIVE_DATASETS):
    """Mark a source connected or disconnected and log what happened."""
    db.execute(
        "INSERT INTO data_sources (name, source_type, fetch_interval, datasets, connection_status) "
        "VALUES (%s, 'daily-feed', '1 day', %s, %s) "
        "ON CONFLICT (name) DO UPDATE SET connection_status = EXCLUDED.connection_status",
        (source, datasets, "connected" if ok else "disconnected"))
    db.execute("INSERT INTO system_logs (actor, action, detail, category) VALUES ('producer', %s, %s, 'pipeline')",
               ("source_fetched" if ok else "source_failed", detail))
    print(detail)


def plan_range(latest, last_stored):
    """(start, end) of the complete days to fetch: after the last stored day, or a full window on the first run."""
    end = min(latest.values())
    start = last_stored + timedelta(days=1) if last_stored else end - timedelta(days=config.WINDOW_DAYS - 1)
    return start, end


def plan_provisional(latest, full_end, last_provisional):
    """(start, end) of the provisional days to fetch: after CHIRPS's last day (and after any provisional day
    already sent) up to the last day both IMERG and ERA5-Land have. start > end when there are none."""
    end = min(latest["imerg"], latest["era5"])
    start = full_end + timedelta(days=1)
    if last_provisional and last_provisional >= start:
        start = last_provisional + timedelta(days=1)
    return start, end


def run_live(interval, dry_run=False):
    try:
        latest = with_retries(earth_engine.latest_days)
        start, end = plan_range(latest, last_live_day())
        p_start, p_end = plan_provisional(latest, end, last_live_day(config.PROVISIONAL_SOURCE))
        newest = f"latest CHIRPS {latest['chirps']}, IMERG {latest['imerg']}, ERA5-Land {latest['era5']}"
        has_full, has_provisional = start <= end, p_start <= p_end
        if not (has_full or has_provisional):
            if dry_run:
                print(f"dry run: up to date to {p_end}; {newest}")
            else:
                record_status(True, f"up to date to {p_end}; {newest}")
            return 0
        first = start if has_full else p_start
        last = p_end if has_provisional else end
        rows = with_retries(lambda: earth_engine.fetch(first, last))
    except Exception as e:  # noqa: BLE001 - reported as a source failure
        detail = f"Earth Engine fetch failed: {type(e).__name__}: {e}"
        if dry_run:
            print(f"dry run: {detail}")
        else:
            record_status(False, detail)
        return 1
    full = [to_live_message(r) for r in rows if has_full and start.isoformat() <= r["date"] <= end.isoformat()]
    provisional = [to_live_message(r, provisional=True) for r in rows
                   if has_provisional and p_start.isoformat() <= r["date"] <= p_end.isoformat()]
    parts = []
    if full:
        parts.append(f"{len(full)} readings for {start} to {end}")
    if provisional:
        parts.append(f"{len(provisional)} provisional readings for {p_start} to {p_end}")
    summary = " and ".join(parts) or "no readings"
    if dry_run:
        for m in (full + provisional)[:3]:
            print(json.dumps(m, indent=2))
        print(f"dry run: {summary} would be sent; {newest}")
        return 0
    publish(full + provisional, interval)
    record_status(True, f"published {summary}; {newest}")
    if provisional:
        record_status(True, f"published {summary}; {newest}", source=config.PROVISIONAL_SOURCE,
                      datasets=config.PROVISIONAL_DATASETS)
    return 0


def forecast_catchments():
    """(name, longitude, latitude) for each active catchment: a point inside its shape."""
    rows = db.query_all(
        "SELECT name, ST_X(p) AS lon, ST_Y(p) AS lat FROM (SELECT name, "
        "ST_PointOnSurface(COALESCE(boundary, geom)) AS p FROM catchment_areas WHERE is_active) s ORDER BY name")
    return [(r["name"], r["lon"], r["lat"]) for r in rows]


def run_forecast(dry_run=False):
    status = {"source": config.FORECAST_SOURCE, "datasets": config.FORECAST_DATASETS}
    try:
        catchments = forecast_catchments()
        issued_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        messages = with_retries(lambda: forecast.fetch(catchments, issued_at))
    except Exception as e:  # noqa: BLE001 - reported as a source failure
        detail = f"Open-Meteo forecast failed: {type(e).__name__}: {e}"
        if dry_run:
            print(f"dry run: {detail}")
        else:
            record_status(False, detail, **status)
        return 1
    peak = max((d["precipitation_mm"] or 0 for m in messages for d in m["days"]), default=0)
    summary = f"{len(messages)} catchments, {config.FORECAST_DAYS} days, highest {peak:.1f} mm"
    if dry_run:
        for m in messages:
            print(json.dumps(m, indent=2))
        print(f"dry run: forecast for {summary} would be sent")
        return 0
    publish(messages, 0, topic=config.TOPIC_FORECASTS)
    record_status(True, f"published forecast for {summary}", **status)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Publish daily readings through Kafka.")
    parser.add_argument("--live", action="store_true", help="Fetch new days from Google Earth Engine.")
    parser.add_argument("--forecast", action="store_true", help="Fetch Open-Meteo rainfall forecasts.")
    parser.add_argument("--start", help="Replay: first date to send, YYYY-MM-DD (default: start of the file).")
    parser.add_argument("--end", help="Replay: last date to send, YYYY-MM-DD (default: end of the file).")
    parser.add_argument("--catchment", help="Replay: send one catchment only, by its database name.")
    parser.add_argument("--interval", type=float, default=0.5, help="Seconds between messages (default 0.5).")
    parser.add_argument("--dry-run", action="store_true", help="Print the first messages instead of sending.")
    args = parser.parse_args()

    if args.live:
        sys.exit(run_live(args.interval, args.dry_run))
    if args.forecast:
        sys.exit(run_forecast(args.dry_run))

    rows = read_rows(args.catchment, args.start, args.end)
    if args.dry_run:
        messages = [to_message(r) for r in rows]
        for m in messages[:3]:
            print(json.dumps(m, indent=2))
        print(f"dry run: {len(messages)} messages would be sent to '{config.TOPIC_RAW_READINGS}'.")
        return
    count = publish((to_message(r) for r in rows), args.interval)
    print(f"done: published {count} readings to '{config.TOPIC_RAW_READINGS}'.")


if __name__ == "__main__":
    main()
