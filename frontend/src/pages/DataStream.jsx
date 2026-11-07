import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import CatchmentMap from "../components/CatchmentMap";
import LineChart from "../components/LineChart";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import { formatCompactTimestamp } from "../formatTimestamp";
import { READINGS, READING_GROUPS, DEFAULT_READINGS } from "../readings";
import { get } from "../api";
import "./DataStream.css";

// The readings the model actually takes, charted side by side on one time axis,
// each with its own scale. Two deliberate choices carried over from the earlier
// version of this screen: never two scales on one chart (the dataviz skill's
// first rule, and the reason rainfall and the other readings stay as separate
// aligned charts rather than one combined plot), and rainfall-like readings as
// bars rather than a line, since a daily total is a discrete quantity and a
// line between two of them implies a reading that was never taken.
//
// There are ten readings and charting all of them at once would be a page of
// scrolling, so they are offered as a picker with four charted by default. That
// also means any one of the model's inputs can be put on screen during a
// demonstration without leaving the page.
const MAX_CHARTS = 6;

// The replay is one reading per catchment per day, so a range is simply that
// many days. "All" is the API's own 500-row cap, not every reading on record.
const RANGES = [
  { key: "30d", label: "30 days", limit: 30 },
  { key: "90d", label: "90 days", limit: 90 },
  { key: "1y", label: "1 year", limit: 365 },
  { key: "all", label: "All", limit: 500, title: "Capped at the 500 most recent readings the API returns" },
];

function pointsFor(readings, featureKey) {
  // The API returns newest first; charts read left-to-right in time.
  return (readings ?? [])
    .filter((row) => row[featureKey] !== null)
    .map((row) => ({ x: new Date(row.recorded_at), y: row[featureKey] }))
    .reverse();
}

export default function DataStream() {
  const [catchments, setCatchments] = useState([]);
  const [catchment, setCatchment] = useState("");
  const [rangeKey, setRangeKey] = useState(RANGES[1].key);
  const [chosen, setChosen] = useState(DEFAULT_READINGS);
  const [readings, setReadings] = useState(null);
  const [tableView, setTableView] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    get("/api/catchments")
      .then((rows) => {
        setCatchments(rows);
        if (rows.length > 0) setCatchment(rows[0].name);
      })
      .catch((err) => setError(err.message));
  }, []);

  const range = RANGES.find((r) => r.key === rangeKey) ?? RANGES[0];

  useEffect(() => {
    if (!catchment) return;
    get("/api/readings/recent", { catchment, limit: range.limit })
      .then((rows) => {
        setReadings(rows);
        setError(null);
      })
      .catch((err) => setError(err.message));
  }, [catchment, range.limit]);

  // Tick a reading on or off, keeping at least one charted and no more than
  // MAX_CHARTS, so the page never empties or turns into endless scrolling.
  function toggleReading(key) {
    setChosen((current) => {
      if (current.includes(key)) {
        return current.length === 1 ? current : current.filter((k) => k !== key);
      }
      return current.length >= MAX_CHARTS ? current : [...current, key];
    });
  }

  const selected = catchments.find((c) => c.name === catchment) ?? null;
  const charted = READINGS.filter((r) => chosen.includes(r.key));

  const windowSpanDays = useMemo(() => {
    if (!readings || readings.length < 2) return null;
    const spanMs = new Date(readings[0].recorded_at) - new Date(readings[readings.length - 1].recorded_at);
    return Math.round(Math.abs(spanMs) / 86400000);
  }, [readings]);

  return (
    <section>
      <PageHeader
        title="Data stream"
        subtitle="The ten readings the model takes, aligned on one time axis"
      />

      <div className="datastream-controls">
        <div className="river-picker">
          {catchments.map((c) => (
            <button
              key={c.id}
              type="button"
              className={c.name === catchment ? "active" : ""}
              onClick={() => setCatchment(c.name)}
            >
              {c.name}
            </button>
          ))}
        </div>

        <div className="range-picker">
          {RANGES.map((r) => (
            <button
              key={r.key}
              type="button"
              title={r.title}
              className={r.key === rangeKey ? "active" : ""}
              onClick={() => setRangeKey(r.key)}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className="reading-picker">
        {READING_GROUPS.map((group) => (
          <div key={group} className="reading-picker-group">
            <span className="reading-picker-label">{group}</span>
            {READINGS.filter((r) => r.group === group).map((reading) => {
              const on = chosen.includes(reading.key);
              return (
                <button
                  key={reading.key}
                  type="button"
                  className={on ? "active" : ""}
                  aria-pressed={on}
                  disabled={!on && chosen.length >= MAX_CHARTS}
                  title={!on && chosen.length >= MAX_CHARTS ? `Up to ${MAX_CHARTS} charts at a time` : undefined}
                  onClick={() => toggleReading(reading.key)}
                >
                  {reading.label}
                </button>
              );
            })}
          </div>
        ))}
      </div>

      <div className="datastream-layout">
        <div className="datastream-main">
          {error && <p className="error">{error}</p>}

          {selected && (
            <div className="datastream-main-header">
              <div>
                <h2 className="panel-title">
                  {selected.name}, {selected.county}
                </h2>
                <span className="panel-caption">
                  Dashed line marks each chart&rsquo;s own peak reading
                </span>
              </div>
              <button type="button" className="table-toggle" onClick={() => setTableView((v) => !v)}>
                {tableView ? "View as chart" : "View as table"}
              </button>
            </div>
          )}

          {readings && readings.length === 0 && (
            <EmptyState>
              No model readings for this catchment yet. Run the producer and consumer to feed it.
            </EmptyState>
          )}

          {readings && readings.length > 0 && (
            <div className="datastream-grid">
              {charted.map((reading) => (
                <LineChart
                  key={reading.key}
                  title={reading.label}
                  unit={reading.unit}
                  variant={reading.variant}
                  points={pointsFor(readings, reading.key)}
                  forceTable={tableView}
                />
              ))}
            </div>
          )}
        </div>

        <aside className="datastream-aside">
          {/* Just the selected river, closely zoomed and labelled, per
              Daniella's Google Maps reference, not the whole-catchments
              view the main dashboard uses: switching rivers here happens
              through the picker above, not by clicking the map. */}
          <CatchmentMap catchments={selected ? [selected] : []} />

          {selected && (
            <div className="panel datastream-detail-card">
              <h3 className="panel-title">{selected.name}</h3>
              <dl className="datastream-detail-grid">
                <dt>County</dt>
                <dd>{selected.county}</dd>

                <dt>Window</dt>
                <dd className="figure">
                  {readings ? `${readings.length} readings` : "—"}
                  {windowSpanDays !== null ? `, about ${windowSpanDays} days` : ""}
                </dd>

                <dt>Interval</dt>
                <dd className="figure">Daily, one reading per catchment</dd>

                <dt>Last reading</dt>
                <dd className="figure">{readings && readings[0] ? formatCompactTimestamp(readings[0].recorded_at) : "—"}</dd>

                <dt>Source</dt>
                <dd>{readings && readings[0] ? `${readings[0].source}, historical replay` : "—"}</dd>
              </dl>

              <Link to={`/alerts?catchment=${encodeURIComponent(selected.name)}`} className="btn-primary datastream-open-alerts">
                Open {selected.name} alerts
              </Link>
            </div>
          )}
        </aside>
      </div>

      {catchments.length === 0 && <EmptyState>Loading catchments.</EmptyState>}
    </section>
  );
}
