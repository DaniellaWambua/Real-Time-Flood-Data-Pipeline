import { useEffect, useState } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import StatTile from "../components/StatTile";
import StatusChip from "../components/StatusChip";
import { severityRole } from "../statusRoles";
import EmptyState from "../components/EmptyState";
import { get } from "../api";
import "./Dashboard.css";

const SEVERITY_RANK = { low: 1, medium: 2, high: 3 };

// Hex values pulled straight from the dataviz skill's reserved status
// palette (theme.css), not re-picked here: Leaflet's CircleMarker takes
// a literal color prop, it cannot read CSS custom properties.
const ROLE_COLOR = {
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
};

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

export default function Dashboard() {
  const [catchments, setCatchments] = useState(null);
  const [activeAlerts, setActiveAlerts] = useState([]);
  const [anomalies, setAnomalies] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      get("/api/catchments"),
      get("/api/alerts", { status: "active", limit: 500 }),
      get("/api/anomalies/recent", { limit: 10 }),
    ])
      .then(([catchmentRows, alertRows, anomalyRows]) => {
        setCatchments(catchmentRows);
        setActiveAlerts(alertRows);
        setAnomalies(anomalyRows);
      })
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!catchments) return null;

  const bounds = catchments.map((c) => [c.latitude, c.longitude]);
  const elevatedCount = catchments.filter(
    (c) => riskRoleFor(c.name, activeAlerts) !== "good",
  ).length;

  return (
    <section>
      <h1>Flood risk overview</h1>

      <div className="stat-row">
        <StatTile label="Active alerts" value={activeAlerts.length} />
        <StatTile
          label="Catchments at elevated risk"
          value={`${elevatedCount} / ${catchments.length}`}
          accent={elevatedCount > 0 ? "var(--status-critical)" : "var(--status-good)"}
        />
      </div>

      <div className="map-card">
        {bounds.length > 0 && (
          <MapContainer bounds={bounds} className="catchment-map" scrollWheelZoom={false}>
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {catchments.map((catchment) => {
              const role = riskRoleFor(catchment.name, activeAlerts);
              return (
                <CircleMarker
                  key={catchment.id}
                  center={[catchment.latitude, catchment.longitude]}
                  radius={10}
                  pathOptions={{
                    color: ROLE_COLOR[role],
                    fillColor: ROLE_COLOR[role],
                    fillOpacity: 0.85,
                  }}
                >
                  <Popup>
                    <strong>{catchment.name}</strong>
                    <br />
                    {catchment.county}
                    <br />
                    <StatusChip role={role} label={role === "good" ? "no active alerts" : role} />
                  </Popup>
                </CircleMarker>
              );
            })}
          </MapContainer>
        )}
      </div>
      <p className="map-caption">
        Coloured by the highest-severity active alert per catchment. Catchment
        positions are still the placeholder coordinates in db/seed.py, not the
        real ERA5/CHIRPS extraction values.
      </p>

      <h2>Recent anomaly outputs</h2>
      {anomalies && anomalies.length === 0 && (
        <EmptyState>
          No anomaly scores yet, real-time LSTM inference is not wired into
          the running system (see project-checklist.md).
        </EmptyState>
      )}
      {anomalies && anomalies.length > 0 && (
        <ul className="anomaly-list">
          {anomalies.map((a) => (
            <li key={a.id}>
              {a.catchment}: score {a.anomaly_score.toFixed(3)} (threshold{" "}
              {a.threshold_used.toFixed(3)}){a.is_anomalous ? ", anomalous" : ""}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
