import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import CatchmentMap from "../components/CatchmentMap";
import RiskDistribution from "../components/RiskDistribution";
import MetricCard from "../components/MetricCard";
import StatusChip from "../components/StatusChip";
import PageHeader from "../components/PageHeader";
import { IconBell, IconBrain, IconChevronRight, IconDatabase, IconMap } from "../components/icons";
import { severityRole } from "../statusRoles";
import EmptyState from "../components/EmptyState";
import { formatReading } from "../readings";
import { get } from "../api";
import { formatWards } from "../wards";
import "./Dashboard.css";

const SEVERITY_RANK = { low: 1, medium: 2, high: 3 };

// Hex values pulled straight from the dataviz skill's reserved status
// palette (theme.css), not re-picked here: Leaflet's CircleMarker takes
// a literal color prop, it cannot read CSS custom properties.
const ROLE_COLOR = {
  good: "#0ca30c",
  warning: "#e5a83b",
  serious: "#ec835a",
  critical: "#e05656",
};

const LEGEND = [
  { role: "good", label: "No active alerts" },
  { role: "warning", label: "Medium severity active" },
  { role: "critical", label: "High severity active" },
];

const RISK_LABEL = { critical: "High", warning: "Medium", good: "No active alert" };

// A catchment's map color is its highest-severity ACTIVE alert right
// now, there is no live LSTM risk score yet (see project-checklist.md,
// "needs a finished training run first"), so this is the most honest
// stand-in for "risk level" available from real data today, not a
// placeholder number. No active alerts reads as "good".
function riskRoleFor(catchmentName, activeAlerts) {
  const matching = activeAlerts.filter((a) => a.catchment === catchmentName);
  if (matching.length === 0) return "good";
  const worst = matching.reduce(
    (max, a) => Math.max(max, SEVERITY_RANK[a.severity] ?? 0),
    0,
  );
  const [role] = Object.entries(SEVERITY_RANK).find(([, rank]) => rank === worst) ?? [];
  return severityRole(role);
}

function CatchmentDetails({ catchment, role, alerts, latestReading, anomalies, onClose }) {
  return (
    <div className="catchment-details">
      <div className="catchment-details-header">
        <div>
          <h3>{catchment.name}</h3>
          <p className="catchment-county">{catchment.county}</p>
          {catchment.wards?.length > 0 && (
            <p className="catchment-wards">Wards: {catchment.wards.join(", ")}</p>
          )}
        </div>
        <button type="button" className="catchment-details-close" onClick={onClose} aria-label="Back to the risk list">
          ✕
        </button>
      </div>
      <StatusChip role={role} label={role === "good" ? "no active alerts" : `${role} risk`} />

      <h4>Active alerts</h4>
      {alerts.length === 0 ? (
        <EmptyState>None right now.</EmptyState>
      ) : (
        <ul className="detail-list">
          {alerts.map((a) => (
            <li key={a.id}>
              <StatusChip role={severityRole(a.severity)} label={a.severity} />
              <span className="detail-time">{new Date(a.created_at).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      )}

      <h4>Latest reading</h4>
      {latestReading ? (
        <dl className="reading-grid">
          <dt>Rainfall</dt>
          <dd>{formatReading(latestReading.rainfall_mm, "rainfall_mm")}</dd>
          <dt>Soil water, 0 to 7 cm</dt>
          <dd>{formatReading(latestReading.soil_1, "soil_1")}</dd>
          <dt>Soil water, 7 to 28 cm</dt>
          <dd>{formatReading(latestReading.soil_2, "soil_2")}</dd>
          <dt>Temperature</dt>
          <dd>{formatReading(latestReading.temp_c, "temp_c")}</dd>
        </dl>
      ) : (
        <EmptyState>No readings recorded for this catchment yet.</EmptyState>
      )}

      <h4>Recent anomaly scores</h4>
      {anomalies.length === 0 ? (
        <EmptyState>
          None yet, real-time LSTM inference is not wired into the running
          system (see project-checklist.md).
        </EmptyState>
      ) : (
        <ul className="detail-list">
          {anomalies.map((a) => (
            <li key={a.id}>
              score {a.anomaly_score.toFixed(3)} (threshold {a.threshold_used.toFixed(3)})
              {a.is_anomalous ? ", anomalous" : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// The rainfall outlook: Open-Meteo's daily forecast per catchment, a rule-based
// warning (KMD's 50 mm in a day) shown apart from the LSTM's alerts.
function RainfallOutlook({ forecast }) {
  const days = [...new Set(forecast.map((f) => f.forecast_date))].sort();
  const byCatchment = new Map();
  for (const f of forecast) {
    if (!byCatchment.has(f.catchment)) byCatchment.set(f.catchment, {});
    byCatchment.get(f.catchment)[f.forecast_date] = f;
  }
  const threshold = forecast[0]?.threshold_mm;
  const issued = forecast.reduce((latest, f) => (f.issued_at > latest ? f.issued_at : latest), "");
  const dayLabel = (d) =>
    new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });

  return (
    <div className="panel dashboard-outlook-panel">
      <div className="panel-header">
        <h2 className="panel-title">Rainfall outlook</h2>
        <span className="panel-caption">
          {forecast.length === 0
            ? "Open-Meteo forecast, not fetched yet"
            : `Open-Meteo forecast, warning at ${threshold} mm in a day, issued ${new Date(issued).toLocaleString()}`}
        </span>
      </div>
      {forecast.length === 0 ? (
        <EmptyState>No forecast stored yet. It appears after the producer's next forecast run.</EmptyState>
      ) : (
        <table className="dashboard-high-severity-table rainfall-outlook-table">
          <thead>
            <tr>
              <th>Catchment</th>
              {days.map((d) => (
                <th key={d}>{dayLabel(d)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...byCatchment.entries()].map(([name, perDay]) => (
              <tr key={name}>
                <td>{name}</td>
                {days.map((d) => {
                  const f = perDay[d];
                  if (!f) return <td key={d}>no forecast</td>;
                  const text = `${f.precipitation_mm.toFixed(1)} mm`;
                  return (
                    <td key={d}>
                      {f.is_warning ? <StatusChip role="warning" label={`${text}, warning`} /> : text}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function RiskList({ catchments, activeAlerts, onSelect }) {
  const ranked = useMemo(() => {
    const rank = { critical: 2, warning: 1, good: 0 };
    return [...catchments]
      .map((c) => ({ catchment: c, role: riskRoleFor(c.name, activeAlerts) }))
      .sort((a, b) => rank[b.role] - rank[a.role]);
  }, [catchments, activeAlerts]);

  return (
    <ul className="risk-list">
      {ranked.map(({ catchment, role }) => (
        <li key={catchment.id}>
          <button type="button" className="risk-list-row" onClick={() => onSelect(catchment.name)}>
            <span className={`risk-list-dot risk-list-dot--${role}`} aria-hidden="true" />
            <span className="risk-list-text">
              <span className="risk-list-name">{catchment.name}</span>
              <span className="risk-list-county">{catchment.county}</span>
            </span>
            <StatusChip role={role} label={RISK_LABEL[role]} />
            <IconChevronRight className="risk-list-chevron" />
          </button>
        </li>
      ))}
    </ul>
  );
}

export default function Dashboard() {
  const [catchments, setCatchments] = useState(null);
  const [activeAlerts, setActiveAlerts] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [sources, setSources] = useState([]);
  const [alertsSummary, setAlertsSummary] = useState(null);
  const [recentHighSeverity, setRecentHighSeverity] = useState([]);
  const [error, setError] = useState(null);
  const [selectedName, setSelectedName] = useState(null);
  const [latestReading, setLatestReading] = useState(null);
  const [forecast, setForecast] = useState([]);

  useEffect(() => {
    Promise.all([
      get("/api/catchments"),
      get("/api/alerts", { status: "active", limit: 500 }),
      get("/api/anomalies/recent", { limit: 50 }),
      get("/api/sources"),
      get("/api/alerts/summary"),
      get("/api/alerts", { severity: "high", limit: 5 }),
    ])
      .then(([catchmentRows, alertRows, anomalyRows, sourceRows, summary, highSeverity]) => {
        setCatchments(catchmentRows);
        setActiveAlerts(alertRows);
        setAnomalies(anomalyRows);
        setSources(sourceRows);
        setAlertsSummary(summary);
        setRecentHighSeverity(highSeverity);
      })
      .catch((err) => setError(err.message));
    // Loaded on its own so a missing forecast never blocks the rest of the screen
    get("/api/forecast")
      .then(setForecast)
      .catch(() => setForecast([]));
  }, []);

  // Clearing the selection resets latestReading from the event that
  // caused it (selectCatchment below), not synchronously inside this
  // effect; the effect's own job is only the fetch for a real selection.
  function selectCatchment(name) {
    setSelectedName(name);
    setLatestReading(null);
  }

  // Fetch the selected catchment's latest reading separately: it is the
  // one piece of detail not already loaded for every catchment up front
  // (readings/recent is per-catchment and potentially large, unlike
  // catchments/alerts/anomalies which are small enough to load whole).
  useEffect(() => {
    if (!selectedName) return;
    get("/api/readings/recent", { catchment: selectedName, limit: 1 })
      .then((rows) => setLatestReading(rows[0] ?? null))
      .catch(() => setLatestReading(null));
  }, [selectedName]);

  const selectedCatchment = useMemo(
    () => catchments?.find((c) => c.name === selectedName) ?? null,
    [catchments, selectedName],
  );

  if (error) return <p className="error">{error}</p>;
  if (!catchments || !alertsSummary) return null;

  const elevated = catchments.filter((c) => riskRoleFor(c.name, activeAlerts) !== "good");
  const elevatedHigh = elevated.filter((c) => riskRoleFor(c.name, activeAlerts) === "critical").length;
  const elevatedMedium = elevated.length - elevatedHigh;

  const connectedSources = sources.filter((s) => s.connection_status === "connected");
  const disconnectedNames = sources
    .filter((s) => s.connection_status !== "connected")
    .map((s) => s.name);

  const selectedRole = selectedCatchment ? riskRoleFor(selectedCatchment.name, activeAlerts) : null;
  const selectedAlerts = selectedCatchment
    ? activeAlerts.filter((a) => a.catchment === selectedCatchment.name)
    : [];
  const selectedAnomalies = selectedCatchment
    ? anomalies.filter((a) => a.catchment === selectedCatchment.name)
    : [];

  return (
    <section>
      <PageHeader
        title="Overview"
        subtitle={`Flood risk across ${catchments.length} monitored catchments`}
      />

      <div className="metric-card-row">
        <MetricCard
          tone="soft"
          glyph={IconMap}
          label="Catchments at elevated risk"
          value={elevated.length}
          valueSuffix={`of ${catchments.length}`}
          segments={[
            { amount: elevatedHigh, color: "var(--status-critical)" },
            { amount: elevatedMedium, color: "var(--status-warning)" },
          ]}
          segmentsTotal={catchments.length}
          description={`${elevatedHigh} high, ${elevatedMedium} medium`}
        />
        <MetricCard
          tone="deep"
          glyph={IconBell}
          label="Active alerts"
          value={alertsSummary.active.toLocaleString()}
          segments={[
            { amount: alertsSummary.by_severity.high.active, color: "var(--status-critical)" },
            { amount: alertsSummary.by_severity.medium.active, color: "var(--status-warning)" },
          ]}
          segmentsTotal={alertsSummary.active}
          description={`${alertsSummary.by_severity.high.active} high, ${alertsSummary.by_severity.medium.active} medium, ${alertsSummary.resolved} resolved`}
        />
        <MetricCard
          tone="soft"
          glyph={IconDatabase}
          label="Data sources connected"
          value={connectedSources.length}
          valueSuffix={`of ${sources.length}`}
          segments={[{ amount: connectedSources.length, color: "var(--status-good)" }]}
          segmentsTotal={sources.length}
          description={
            disconnectedNames.length > 0
              ? `${disconnectedNames.join(", ")} ${disconnectedNames.length === 1 ? "is" : "are"} disconnected`
              : (connectedSources.find((s) => s.datasets)?.datasets ?? "All data sources connected")
          }
        />
        <MetricCard
          tone="deep"
          glyph={IconBrain}
          label="LSTM anomaly results"
          value={anomalies.length}
          badge={{ role: "good", glyph: "●", label: "Scoring" }}
          description="Risk on this screen comes from the model's flagged days"
        />
      </div>

      <div className="dashboard-main-row">
        <div className="panel dashboard-map-panel">
          <div className="panel-header">
            <h2 className="panel-title">Catchment risk map</h2>
            <span className="panel-caption">Colour shows the highest active alert in each catchment</span>
          </div>

          <CatchmentMap
            catchments={catchments}
            selectedName={selectedName}
            onSelect={selectCatchment}
            colorFor={(catchment) => ROLE_COLOR[riskRoleFor(catchment.name, activeAlerts)]}
            mapClassName="catchment-map--tall"
          />

          <div className="map-legend">
            {LEGEND.map((item) => (
              <StatusChip key={item.role} role={item.role} label={item.label} />
            ))}
          </div>
        </div>

        <aside className="panel dashboard-risk-panel">
          {selectedCatchment ? (
            <CatchmentDetails
              catchment={selectedCatchment}
              role={selectedRole}
              alerts={selectedAlerts}
              latestReading={latestReading}
              anomalies={selectedAnomalies}
              onClose={() => selectCatchment(null)}
            />
          ) : (
            <>
              <div className="panel-header">
                <h2 className="panel-title">Catchments by risk</h2>
                <span className="panel-caption">Highest first</span>
              </div>
              <RiskDistribution
                total={catchments.length}
                segments={[
                  { role: "critical", label: "High", count: elevatedHigh },
                  { role: "warning", label: "Medium", count: elevatedMedium },
                  { role: "good", label: "No active alert", count: catchments.length - elevated.length },
                ]}
              />
              <RiskList catchments={catchments} activeAlerts={activeAlerts} onSelect={selectCatchment} />
            </>
          )}
        </aside>
      </div>

      <RainfallOutlook forecast={forecast} />

      <div className="panel dashboard-high-severity-panel">
        <div className="panel-header">
          <h2 className="panel-title">Latest high-severity alerts</h2>
          <Link to="/alerts?severity=high" className="panel-link">
            View all {alertsSummary.by_severity.high.active + alertsSummary.by_severity.high.resolved} high-severity alerts
          </Link>
        </div>

        {recentHighSeverity.length === 0 ? (
          <EmptyState>No high-severity alerts right now.</EmptyState>
        ) : (
          <table className="dashboard-high-severity-table">
            <thead>
              <tr>
                <th>Severity</th>
                <th>Catchment</th>
                <th>Status</th>
                <th>Raised</th>
              </tr>
            </thead>
            <tbody>
              {recentHighSeverity.map((alert) => (
                <tr key={alert.id}>
                  <td>
                    <StatusChip role={severityRole(alert.severity)} label={alert.severity} />
                  </td>
                  <td>
                    {alert.catchment}
                    {alert.wards?.length > 0 && <span className="alert-wards">{formatWards(alert.wards)}</span>}
                  </td>
                  <td>
                    <StatusChip
                      role={alert.status === "resolved" ? "good" : "active"}
                      label={alert.status}
                    />
                  </td>
                  <td>{new Date(alert.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
