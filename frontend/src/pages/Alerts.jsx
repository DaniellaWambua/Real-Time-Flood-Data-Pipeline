import { Fragment, useEffect, useState } from "react";
import { formatWards } from "../wards";
import { useOutletContext, useSearchParams } from "react-router-dom";
import StatusChip from "../components/StatusChip";
import PageHeader from "../components/PageHeader";
import { severityRole, alertStatusRole } from "../statusRoles";
import EmptyState from "../components/EmptyState";
import AlertResponses from "./AlertResponses";
import { get, patch } from "../api";
import "./Alerts.css";

// Descending, for the filter tabs (matches the reference mockup -
// the queue is meant to be worked from high severity down).
const TAB_SEVERITIES = ["high", "medium", "low"];
const SEVERITY_LABEL = { low: "Low", medium: "Medium", high: "High" };
const STATUSES = ["active", "acknowledged", "resolved"];

// GET /api/alerts has no offset/page param, just a row limit (capped
// at 500 server-side) - "Load more" below works by asking the same
// endpoint for a bigger limit, not by paging forward.
const PAGE_SIZE = 20;
const MAX_LIMIT = 500;

const EMPTY_SUMMARY = {
  total: 0,
  active: 0,
  acknowledged: 0,
  resolved: 0,
  low: 0,
  medium: 0,
  high: 0,
  by_severity: {
    low: { active: 0, acknowledged: 0, resolved: 0 },
    medium: { active: 0, acknowledged: 0, resolved: 0 },
    high: { active: 0, acknowledged: 0, resolved: 0 },
  },
};

function formatTimestamp(iso) {
  return new Date(iso).toLocaleString();
}

// A flood day is stored as midnight UTC, so show the date only, read in UTC
function formatDay(iso) {
  return new Date(iso).toLocaleDateString("en-GB", { timeZone: "UTC" });
}

function heroHint(acknowledged, resolved, total) {
  if (acknowledged === 0 && resolved === 0) {
    return "No alert has been acknowledged or resolved yet. Work the queue from high severity down.";
  }
  return `${acknowledged} acknowledged and ${resolved} of ${total} resolved so far. Keep working the queue from high severity down.`;
}

// Which alerts an action can be applied to, matching the backend's rules
const ACTION_FROM = { acknowledge: ["active"], resolve: ["active", "acknowledged"] };

// Only Emergency Responders can acknowledge or resolve (PATCH /api/alerts/<id>);
// other roles see the same queue read-only.
export default function Alerts() {
  const { user } = useOutletContext();
  const canAct = user.role === "emergency_responder";
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
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
  const [openId, setOpenId] = useState(null);
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
  }, [filters, visibleLimit, refresh]);

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
  }, [filters.catchment, refresh]);

  // Send one action for each eligible alert, then reload the list and the counts
  async function act(action, ids) {
    const eligible = (alerts ?? []).filter((a) => ids.includes(a.id) && ACTION_FROM[action].includes(a.status));
    if (eligible.length === 0) return;
    setBusy(true);
    try {
      await Promise.all(eligible.map((a) => patch(`/api/alerts/${a.id}`, { action })));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
      setRefresh((n) => n + 1);
    }
  }

  function eligibleCount(action) {
    return (alerts ?? []).filter((a) => selectedIds.has(a.id) && ACTION_FROM[action].includes(a.status)).length;
  }

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

  // Both filters back to "All" in one step, and one URL update rather than two.
  function clearFilters() {
    setVisibleLimit(PAGE_SIZE);
    setFilters((current) => {
      const next = { ...current, catchment: "", status: "" };
      setSearchParams(next.severity ? { severity: next.severity } : {});
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
            {summary.acknowledged} acknowledged, {summary.resolved} of {summary.total.toLocaleString()} resolved
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
                <span className="alert-hero-legend-glyph" style={{ color: "var(--text-muted)" }} aria-hidden="true">
                  ●
                </span>
                Acknowledged
              </span>
              <strong className="figure">{summary.acknowledged}</strong>
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

          <p className="alert-hero-hint">{heroHint(summary.acknowledged, summary.resolved, summary.total)}</p>
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
          {/* Label inside the pill, arrow next to the value, and a filter that
              is set reads differently from one left on "All" - replacing the
              two wide boxes with the label stacked above them. */}
          <label className={`pill-select${filters.catchment ? " pill-select--set" : ""}`}>
            <span className="pill-select-key">Catchment</span>
            <select value={filters.catchment} onChange={(e) => updateFilter("catchment", e.target.value)}>
              <option value="">All</option>
              {catchments.map((c) => (
                <option key={c.id} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>

          <label className={`pill-select${filters.status ? " pill-select--set" : ""}`}>
            <span className="pill-select-key">Status</span>
            <select value={filters.status} onChange={(e) => updateFilter("status", e.target.value)}>
              <option value="">All</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>

          {(filters.catchment || filters.status) && (
            <button
              type="button"
              className="alert-filter-clear"
              onClick={clearFilters}
            >
              Clear filters
            </button>
          )}

          {canAct ? (
            <div className="alert-bulk-actions">
              <button
                type="button"
                disabled={busy || eligibleCount("acknowledge") === 0}
                onClick={() => act("acknowledge", [...selectedIds])}
              >
                Acknowledge selected
              </button>
              <button
                type="button"
                disabled={busy || eligibleCount("resolve") === 0}
                onClick={() => act("resolve", [...selectedIds])}
              >
                Resolve selected
              </button>
            </div>
          ) : (
            <p className="alert-readonly-note">Only Emergency Responders can acknowledge or resolve alerts.</p>
          )}
        </div>

        {error && <p className="error">{error}</p>}

        {alerts && alerts.length === 0 && <EmptyState>No alerts match these filters.</EmptyState>}

        {alerts && alerts.length > 0 && (
          <table className="alert-table">
            <thead>
              <tr>
                {canAct && (
                  <th className="alert-table-checkbox-cell">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={toggleSelectAll}
                      aria-label="Select all alerts"
                    />
                  </th>
                )}
                <th>Severity</th>
                <th>Catchment</th>
                <th>Flood day</th>
                <th>Score / threshold</th>
                <th>Status</th>
                <th>Updated</th>
                <th>Responses</th>
                {canAct && <th aria-hidden="true" />}
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert) => (
                <Fragment key={alert.id}>
                <tr>
                  {canAct && (
                    <td className="alert-table-checkbox-cell">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(alert.id)}
                        onChange={() => toggleSelected(alert.id)}
                        aria-label={`Select alert ${alert.id}`}
                      />
                    </td>
                  )}
                  <td>
                    <StatusChip role={severityRole(alert.severity)} label={alert.severity} />
                  </td>
                  <td>
                    {alert.catchment}
                    {alert.wards?.length > 0 && <span className="alert-wards">{formatWards(alert.wards)}</span>}
                  </td>
                  <td className="figure">{formatDay(alert.flood_day)}</td>
                  <td className="figure">
                    {alert.anomaly_score.toFixed(3)} / {alert.threshold_used.toFixed(3)}
                  </td>
                  <td>
                    <StatusChip role={alertStatusRole(alert)} label={alert.status} />
                  </td>
                  <td className="figure">
                    {formatTimestamp(alert.updated_at)}
                    {(alert.resolved_by || alert.acknowledged_by) && (
                      <span className="alert-table-by"> by {alert.resolved_by || alert.acknowledged_by}</span>
                    )}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="alert-responses-toggle"
                      aria-expanded={openId === alert.id}
                      onClick={() => setOpenId((id) => (id === alert.id ? null : alert.id))}
                    >
                      {alert.responses > 0 ? `${alert.responses} recorded` : "Record"}
                    </button>
                  </td>
                  {canAct && (
                    <td className="alert-table-row-actions">
                      <button
                        type="button"
                        disabled={busy || alert.status !== "active"}
                        onClick={() => act("acknowledge", [alert.id])}
                      >
                        Acknowledge
                      </button>
                      <button
                        type="button"
                        disabled={busy || alert.status === "resolved"}
                        onClick={() => act("resolve", [alert.id])}
                      >
                        Resolve
                      </button>
                    </td>
                  )}
                </tr>
                {openId === alert.id && (
                  <tr className="alert-responses-row">
                    <td colSpan={canAct ? 9 : 7}>
                      <AlertResponses alert={alert} role={user.role} onAdded={() => setRefresh((n) => n + 1)} />
                    </td>
                  </tr>
                )}
                </Fragment>
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
