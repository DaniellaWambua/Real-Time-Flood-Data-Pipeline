import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import CatchmentMap from "../components/CatchmentMap";
import LineChart from "../components/LineChart";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import { formatCompactTimestamp } from "../formatTimestamp";
import { get } from "../api";
import "./DataStream.css";

// All four features side by side on one page, each as its own
// small-multiple chart with its own axis, rather than a single
// feature + dropdown. This mirrors the Power BI reference dashboard
// Daniella shared (a river's metrics together on one screen, a river
// picker to the side) with one deliberate change: that reference
// combines rainfall and water level on shared dual axes, which the
// dataviz skill treats as the single most common charting mistake
// (two y-scales on one chart). Rainfall (mm) and river discharge
// (m3/s) are different scales here too, so they stay as separate
// charts instead. Rainfall is discrete event data, so it renders as
// bars rather than a connected line; the other three are continuous
// readings and keep the line (with an area fill).
const FEATURES = [
  { key: "rainfall_mm", label: "Rainfall", unit: "mm", variant: "bars" },
  { key: "river_discharge_m3s", label: "River discharge", unit: "m3/s", variant: "line" },
  { key: "soil_moisture_m3m3", label: "Soil moisture", unit: "m3/m3", variant: "line" },
  { key: "evaporation_mm", label: "Evaporation", unit: "mm", variant: "line" },
];

// GET /api/readings/recent only takes a row limit, not a date range,
// so "7 days"/"30 days" are approximated from the dataset's own
// 3-hourly cadence rather than a real server-side date filter; "All"
// is the API's own 500-row cap, the most it will ever return in one
// page, not literally every reading on record.
const RANGES = [
  { key: "latest200", label: "Latest 200", limit: 200 },
  { key: "7d", label: "7 days", limit: 56 },
  { key: "30d", label: "30 days", limit: 240 },
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
  const [rangeKey, setRangeKey] = useState(RANGES[0].key);
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

  const selected = catchments.find((c) => c.name === catchment) ?? null;

  // Interval is measured from the data itself (consecutive readings'
  // own timestamps), not assumed, so this stays correct even if the
  // dataset's cadence ever changes.
  const intervalHours = useMemo(() => {
    if (!readings || readings.length < 2) return null;
    const diffMs = new Date(readings[0].recorded_at) - new Date(readings[1].recorded_at);
    return Math.round(Math.abs(diffMs) / 3600000);
  }, [readings]);

  const windowSpanDays = useMemo(() => {
    if (!readings || readings.length < 2) return null;
    const spanMs = new Date(readings[0].recorded_at) - new Date(readings[readings.length - 1].recorded_at);
    return Math.round(Math.abs(spanMs) / 86400000);
  }, [readings]);

  return (
    <section>
      <PageHeader
        title="Data stream"
        subtitle="Rainfall, river discharge, soil moisture and evaporation, aligned on one time axis"
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

          {readings && (
            <div className="datastream-grid">
              {FEATURES.map((feature) => (
                <LineChart
                  key={feature.key}
                  title={feature.label}
                  unit={feature.unit}
                  variant={feature.variant}
                  points={pointsFor(readings, feature.key)}
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
                <dd className="figure">{intervalHours !== null ? `${intervalHours}-hourly` : "—"}</dd>

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
