import { useEffect, useState } from "react";
import StatusChip from "../components/StatusChip";
import { severityRole, alertStatusRole } from "../statusRoles";
import EmptyState from "../components/EmptyState";
import { get } from "../api";
import "./Alerts.css";

const SEVERITIES = ["low", "medium", "high"];
const STATUSES = ["active", "resolved"];

function formatTimestamp(iso) {
  return new Date(iso).toLocaleString();
}

export default function Alerts() {
  const [catchments, setCatchments] = useState([]);
  const [filters, setFilters] = useState({ severity: "", catchment: "", status: "" });
  const [alerts, setAlerts] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    get("/api/catchments")
      .then(setCatchments)
      .catch(() => setCatchments([]));
  }, []);

  useEffect(() => {
    get("/api/alerts", filters)
      .then((rows) => {
        setAlerts(rows);
        setError(null);
      })
      .catch((err) => setError(err.message));
  }, [filters]);

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  return (
    <section>
      <h1>Alert management</h1>

      {/* Filters in one row above the list, per the alert management screen's
          proposal wireframe (3.4.6): severity, catchment and time are all
          already supported by GET /api/alerts, "time" here is the created_at
          column sort, there is no date-range picker yet. */}
      <div className="filter-row">
        <label>
          Severity
          <select value={filters.severity} onChange={(e) => updateFilter("severity", e.target.value)}>
            <option value="">All</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>

        <label>
          Catchment
          <select value={filters.catchment} onChange={(e) => updateFilter("catchment", e.target.value)}>
            <option value="">All</option>
            {catchments.map((c) => (
              <option key={c.id} value={c.name}>
                {c.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Status
          <select value={filters.status} onChange={(e) => updateFilter("status", e.target.value)}>
            <option value="">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="error">{error}</p>}

      {alerts && alerts.length === 0 && (
        <EmptyState>No alerts match these filters.</EmptyState>
      )}

      {alerts && alerts.length > 0 && (
        <table className="alert-table">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Catchment</th>
              <th>Status</th>
              <th>Raised</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((alert) => (
              <tr key={alert.id}>
                <td>
                  <StatusChip role={severityRole(alert.severity)} label={alert.severity} />
                </td>
                <td>{alert.catchment}</td>
                <td>
                  <StatusChip role={alertStatusRole(alert)} label={alert.status} />
                </td>
                <td>{formatTimestamp(alert.created_at)}</td>
                <td>{formatTimestamp(alert.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
