import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import StatusChip from "../components/StatusChip";
import PageHeader from "../components/PageHeader";
import { severityRole, alertStatusRole } from "../statusRoles";
import EmptyState from "../components/EmptyState";
import { get } from "../api";
import "./Alerts.css";

// Descending, for the filter tabs (matches the reference mockup -
// the queue is meant to be worked from high severity down).
const TAB_SEVERITIES = ["high", "medium", "low"];
const SEVERITY_LABEL = { low: "Low", medium: "Medium", high: "High" };
const STATUSES = ["active", "resolved"];

// GET /api/alerts has no offset/page param, just a row limit (capped
// at 500 server-side) - "Load more" below works by asking the same
// endpoint for a bigger limit, not by paging forward.
const PAGE_SIZE = 20;
const MAX_LIMIT = 500;

const EMPTY_SUMMARY = {
  total: 0,
  active: 0,
  resolved: 0,
  low: 0,
  medium: 0,
  high: 0,
  by_severity: {
    low: { active: 0, resolved: 0 },
    medium: { active: 0, resolved: 0 },
    high: { active: 0, resolved: 0 },
  },
};

function formatTimestamp(iso) {
  return new Date(iso).toLocaleString();
}

// The hero's hint line changes once something has actually been
// resolved; nothing in the real data has been yet, so only the first
// branch is seen today, but the second keeps the message honest once
// it stops being true.
function heroHint(resolved, total) {
  if (resolved === 0) {
    return "No alert has been acknowledged or resolved yet. Work the queue from high severity down.";
  }
  return `${resolved} of ${total} alerts resolved so far. Keep working the queue from high severity down.`;
}

// Browsing itself stays read-only by design: GET /api/alerts has no
// matching PATCH, so there is nothing for Acknowledge/Resolve to
// actually persist yet. Per Daniella's confirmed "visual-only" choice
// (the same one behind Admin's Reconnect button), the checkboxes and
// selection state below are real - they are just local UI state - but
// the Acknowledge/Resolve controls themselves are deliberately inert:
// they render exactly like the reference layout (including the bulk
// buttons disabling themselves when nothing is selected, which is
// genuine behavior, not a fake limitation) without claiming to write
// anything back to the server.
export default function Alerts() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [catchments, setCatchments] = useState([]);
  const [filters, setFilters] = useState({
    severity: searchParams.get("severity") ?? "",
    catchment: searchParams.get("catchment") ?? "",
    status: searchParams.get("status") ?? "",
  });
  const [visibleLimit, setVisibleLimit] = useState(PAGE_SIZE);
  const [alerts, setAlerts] = useState(null);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [error, setError] = useState(null);
  const [summary, setSummary] = useState(EMPTY_SUMMARY);

  useEffect(() => {
    get("/api/catchments")
      .then(setCatchments)
      .catch(() => setCatchments([]));
  }, []);

  useEffect(() => {
    get("/api/alerts", { ...filters, limit: visibleLimit })
      .then((rows) => {
        setAlerts(rows);
        setSelectedIds(new Set());
        setError(null);
      })
      .catch((err) => setError(err.message));
  }, [filters, visibleLimit]);

  // The hero numbers read the whole matching set counted in SQL
  // (GET /api/alerts/summary), not the rows /api/alerts hands back -
  // that list is capped at 500, which the real seeded data (1,828
  // alerts) blows past, so counting its rows would silently undercount.
  // Scoped to catchment only, same as /api/alerts/summary itself
  // (severity/status are what the tabs and table break down, not
  // something to also filter the summary by).
  useEffect(() => {
    get("/api/alerts/summary", { catchment: filters.catchment })
      .then(setSummary)
      .catch(() => setSummary(EMPTY_SUMMARY));
  }, [filters.catchment]);

  // Changing a filter re-seeds the URL (not just local state), so the
  // cross-page links this page is a destination for - Dashboard's
  // "/alerts?severity=high" and DataStream's "/alerts?catchment=X" -
  // stay shareable/bookmarkable from here too, not just on arrival.
  function updateFilter(key, value) {
    setVisibleLimit(PAGE_SIZE);
    setFilters((current) => {
      const next = { ...current, [key]: value };
      const params = {};
      if (next.severity) params.severity = next.severity;
      if (next.catchment) params.catchment = next.catchment;
      if (next.status) params.status = next.status;
      setSearchParams(params);
      return next;
    });
  }

  function toggleSelected(id) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    setSelectedIds((current) => {
      if (alerts && current.size === alerts.length) return new Set();
      return new Set((alerts ?? []).map((a) => a.id));
    });
  }

  const canLoadMore = alerts && alerts.length === visibleLimit && visibleLimit < MAX_LIMIT;
  const allSelected = alerts && alerts.length > 0 && selectedIds.size === alerts.length;
  const activeTotal = summary.active || 1;

  return (
    <section>
      <PageHeader
        title="Alerts"
        subtitle="Triage and track flood alerts across monitored catchments"
      />

      <div className="panel alert-hero">
        <div className="alert-hero-main">
          <span className="alert-hero-label">Active alerts</span>
          <span className="alert-hero-value">{summary.active.toLocaleString()}</span>
          <p className="alert-hero-resolved">
            {summary.resolved} of {summary.total.toLocaleString()} resolved
          </p>
        </div>

        <div className="alert-hero-breakdown">
          <div className="alert-hero-bar" role="presentation">
            <div
              className="alert-hero-bar-segment"
              style={{
                width: `${(summary.by_severity.high.active / activeTotal) * 100}%`,
                background: "var(--status-critical)",
              }}
            />
            <div
              className="alert-hero-bar-segment"
              style={{
                width: `${(summary.by_severity.medium.active / activeTotal) * 100}%`,
                background: "var(--status-warning)",
              }}
            />
            <div
              className="alert-hero-bar-segment"
              style={{
                width: `${(summary.by_severity.low.active / activeTotal) * 100}%`,
                background: "var(--status-good)",
              }}
            />
          </div>

          <div className="alert-hero-legend">
            <span className="alert-hero-legend-item">
              <span className="alert-hero-legend-key">
                <span className="alert-hero-legend-glyph" style={{ color: "var(--status-critical)" }} aria-hidden="true">
                  ◆
                </span>
                High
              </span>
              <strong className="figure">{summary.by_severity.high.active}</strong>
            </span>
            <span className="alert-hero-legend-item">
              <span className="alert-hero-legend-key">
                <span className="alert-hero-legend-glyph" style={{ color: "var(--status-warning)" }} aria-hidden="true">
                  ▲
                </span>
                Medium
              </span>
              <strong className="figure">{summary.by_severity.medium.active}</strong>
            </span>
            <span className="alert-hero-legend-item">
              <span className="alert-hero-legend-key">
                <span className="alert-hero-legend-glyph" style={{ color: "var(--status-good)" }} aria-hidden="true">
                  ○
                </span>
                Low
              </span>
              <strong className="figure">{summary.by_severity.low.active}</strong>
            </span>
            <span className="alert-hero-legend-item">
              <span className="alert-hero-legend-key">
                <span className="alert-hero-legend-glyph" style={{ color: "var(--status-good)" }} aria-hidden="true">
                  ✓
                </span>
                Resolved
              </span>
              <strong className="figure">{summary.resolved}</strong>
            </span>
          </div>

          <p className="alert-hero-hint">{heroHint(summary.resolved, summary.total)}</p>
        </div>
      </div>

      <div className="panel alert-list-panel">
        <div className="severity-tabs">
          <button
            type="button"
            className={filters.severity === "" ? "active" : ""}
            onClick={() => updateFilter("severity", "")}
          >
            All <span className="severity-tab-count figure">{summary.total}</span>
          </button>
          {TAB_SEVERITIES.map((s) => (
            <button
              key={s}
              type="button"
              className={filters.severity === s ? "active" : ""}
              onClick={() => updateFilter("severity", s)}
            >
              {SEVERITY_LABEL[s]} <span className="severity-tab-count figure">{summary[s]}</span>
            </button>
          ))}
        </div>

        <div className="alert-filter-row">
          <label>
            Catchment
            <select value={filters.catchment} onChange={(e) => updateFilter("catchment", e.target.value)}>
              <option value="">All catchments</option>
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
              <option value="">All statuses</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>

          <div className="alert-bulk-actions">
            <button
              type="button"
              disabled={selectedIds.size === 0}
              title="Not available yet - there's no backend endpoint to acknowledge alerts in bulk"
            >
              Acknowledge selected
            </button>
            <button
              type="button"
              disabled={selectedIds.size === 0}
              title="Not available yet - there's no backend endpoint to resolve alerts in bulk"
            >
              Resolve selected
            </button>
          </div>
        </div>

        {error && <p className="error">{error}</p>}

        {alerts && alerts.length === 0 && <EmptyState>No alerts match these filters.</EmptyState>}

        {alerts && alerts.length > 0 && (
          <table className="alert-table">
            <thead>
              <tr>
                <th className="alert-table-checkbox-cell">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleSelectAll}
                    aria-label="Select all alerts"
                  />
                </th>
                <th>Severity</th>
                <th>Catchment</th>
                <th>Status</th>
                <th>Raised</th>
                <th>Updated</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert) => (
                <tr key={alert.id}>
                  <td className="alert-table-checkbox-cell">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(alert.id)}
                      onChange={() => toggleSelected(alert.id)}
                      aria-label={`Select alert ${alert.id}`}
                    />
                  </td>
                  <td>
                    <StatusChip role={severityRole(alert.severity)} label={alert.severity} />
                  </td>
                  <td>{alert.catchment}</td>
                  <td>
                    <StatusChip role={alertStatusRole(alert)} label={alert.status} />
                  </td>
                  <td className="figure">{formatTimestamp(alert.created_at)}</td>
                  <td className="figure">{formatTimestamp(alert.updated_at)}</td>
                  <td className="alert-table-row-actions">
                    <button type="button" title="Not available yet - there's no backend endpoint to acknowledge an alert">
                      Acknowledge
                    </button>
                    <button type="button" title="Not available yet - there's no backend endpoint to resolve an alert">
                      Resolve
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {alerts && alerts.length > 0 && (
        <div className="alert-list-footer">
          <span className="alert-list-footer-note">
            Showing the {alerts.length} most recent of {summary.total.toLocaleString()}. Filter by
            catchment or status to narrow the queue.
          </span>
          {canLoadMore && (
            <button
              type="button"
              onClick={() => setVisibleLimit((n) => Math.min(n + PAGE_SIZE, MAX_LIMIT))}
            >
              Load more
            </button>
          )}
        </div>
      )}
    </section>
  );
}
