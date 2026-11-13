import { Fragment, useEffect, useState } from "react";
import { useOutletContext, useSearchParams } from "react-router-dom";
import StatusChip from "../components/StatusChip";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import IncidentDetail from "./IncidentDetail";
import { severityRole, alertStatusRole, verificationRole } from "../statusRoles";
import { confirmationTag, raisedAfter } from "../provisional";
import { formatWards } from "../wards";
import { formatSpan } from "../incidentFormat";
import { get, post } from "../api";
import "./Incidents.css";

// Consecutive flagged days in one catchment form an incident. Disaster Management verifies or
// dismisses each one; only verified incidents reach Emergency Responders and Government Officials.
// Responders acknowledge and resolve, recording what they found (IncidentDetail.jsx).
const TAB_SEVERITIES = ["high", "medium", "low"];
const SEVERITY_LABEL = { low: "Low", medium: "Medium", high: "High" };
const STATUSES = ["active", "acknowledged", "resolved"];
const VERIFICATIONS = ["pending", "verified", "dismissed"];
const PAGE_SIZE = 20;
const MAX_LIMIT = 500;

const EMPTY_SUMMARY = {
  total: 0, pending: 0, verified: 0, dismissed: 0, active: 0, acknowledged: 0, resolved: 0,
  low: 0, medium: 0, high: 0,
  by_severity: {
    low: { active: 0, acknowledged: 0, resolved: 0 },
    medium: { active: 0, acknowledged: 0, resolved: 0 },
    high: { active: 0, acknowledged: 0, resolved: 0 },
  },
};

export default function Incidents() {
  const { user } = useOutletContext();
  const role = user.role;
  const canVerify = role === "disaster_management_agency";
  const canAct = role === "emergency_responder";
  const seesAll = role === "disaster_management_agency" || role === "system_administrator";
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState({
    severity: searchParams.get("severity") ?? "",
    catchment: searchParams.get("catchment") ?? "",
    status: searchParams.get("status") ?? "",
    verification: searchParams.get("verification") ?? (canVerify ? "pending" : ""),
  });
  const [openId, setOpenId] = useState(() => Number(searchParams.get("id")) || null);
  const [visibleLimit, setVisibleLimit] = useState(PAGE_SIZE);
  const [rows, setRows] = useState(null);
  const [summary, setSummary] = useState(EMPTY_SUMMARY);
  const [catchments, setCatchments] = useState([]);
  const [selected, setSelected] = useState(() => new Set());
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    get("/api/catchments").then(setCatchments).catch(() => setCatchments([]));
  }, []);

  useEffect(() => {
    get("/api/incidents", { ...filters, limit: visibleLimit })
      .then((list) => {
        setRows(list);
        setSelected(new Set());
        setError(null);
      })
      .catch((err) => setError(err.message));
  }, [filters, visibleLimit, refresh]);

  useEffect(() => {
    get("/api/incidents/summary", { catchment: filters.catchment })
      .then(setSummary)
      .catch(() => setSummary(EMPTY_SUMMARY));
  }, [filters.catchment, refresh]);

  function updateFilter(key, value) {
    setVisibleLimit(PAGE_SIZE);
    setFilters((current) => {
      const next = { ...current, [key]: value };
      setSearchParams(Object.fromEntries(Object.entries(next).filter(([, v]) => v)));
      return next;
    });
  }

  function toggleSelected(id) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // Bulk actions, each only on the selected incidents it applies to
  const eligible = {
    verify: (i) => i.verification === "pending",
    dismiss: (i) => i.verification === "pending",
    acknowledge: (i) => i.status === "active",
  };

  async function bulk(action) {
    const targets = (rows ?? []).filter((i) => selected.has(i.id) && eligible[action](i));
    if (targets.length === 0) return;
    setBusy(true);
    try {
      await Promise.all(
        targets.map((i) =>
          action === "acknowledge"
            ? post(`/api/incidents/${i.id}/acknowledge`, {})
            : post(`/api/incidents/${i.id}/verification`, { decision: action }),
        ),
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
      setRefresh((n) => n + 1);
    }
  }

  function countEligible(action) {
    return (rows ?? []).filter((i) => selected.has(i.id) && eligible[action](i)).length;
  }

  const hasCheckboxes = canVerify || canAct;
  const columns = 8 + (hasCheckboxes ? 1 : 0);
  const canLoadMore = rows && rows.length === visibleLimit && visibleLimit < MAX_LIMIT;
  const activeTotal = summary.active || 1;
  const heroValue = canVerify ? summary.pending : summary.active;

  return (
    <section>
      <PageHeader
        title="Incidents"
        subtitle={
          canVerify
            ? "Check each new incident and verify it before responders and officials are told"
            : "Verified flood incidents across monitored catchments"
        }
      />

      <div className="panel alert-hero">
        <div className="alert-hero-main">
          <span className="alert-hero-label">{canVerify ? "Waiting for verification" : "Active incidents"}</span>
          <span className="alert-hero-value">{heroValue.toLocaleString()}</span>
          <p className="alert-hero-resolved">
            {summary.acknowledged} acknowledged, {summary.resolved} resolved
            {seesAll && `, ${summary.dismissed} dismissed`}
          </p>
        </div>
        <div className="alert-hero-breakdown">
          <div className="alert-hero-bar" role="presentation">
            {[
              ["high", "var(--status-critical)"],
              ["medium", "var(--status-warning)"],
              ["low", "var(--status-good)"],
            ].map(([sev, color]) => (
              <div
                key={sev}
                className="alert-hero-bar-segment"
                style={{ width: `${(summary.by_severity[sev].active / activeTotal) * 100}%`, background: color }}
              />
            ))}
          </div>
          <p className="alert-hero-hint">
            {canVerify
              ? "Verify an incident when the readings and any reports support it; dismiss it as a false alarm otherwise. Only verified incidents reach the field."
              : canAct
                ? "Acknowledge an incident once seen. When you resolve it, say whether flooding was found: that report trains the next model."
                : "Record the resources you allocate against each incident."}
          </p>
        </div>
      </div>

      <div className="panel alert-list-panel">
        <div className="severity-tabs">
          <button type="button" className={filters.severity === "" ? "active" : ""} onClick={() => updateFilter("severity", "")}>
            All <span className="severity-tab-count figure">{summary.total - summary.dismissed}</span>
          </button>
          {TAB_SEVERITIES.map((s) => (
            <button key={s} type="button" className={filters.severity === s ? "active" : ""} onClick={() => updateFilter("severity", s)}>
              {SEVERITY_LABEL[s]} <span className="severity-tab-count figure">{summary[s]}</span>
            </button>
          ))}
        </div>

        <div className="alert-filter-row">
          <label className={`pill-select${filters.catchment ? " pill-select--set" : ""}`}>
            <span className="pill-select-key">Catchment</span>
            <select value={filters.catchment} onChange={(e) => updateFilter("catchment", e.target.value)}>
              <option value="">All</option>
              {catchments.map((c) => (
                <option key={c.id} value={c.name}>{c.name}</option>
              ))}
            </select>
          </label>
          <label className={`pill-select${filters.status ? " pill-select--set" : ""}`}>
            <span className="pill-select-key">Status</span>
            <select value={filters.status} onChange={(e) => updateFilter("status", e.target.value)}>
              <option value="">All</option>
              <option value="open">open</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </label>
          {seesAll && (
            <label className={`pill-select${filters.verification ? " pill-select--set" : ""}`}>
              <span className="pill-select-key">Verification</span>
              <select value={filters.verification} onChange={(e) => updateFilter("verification", e.target.value)}>
                <option value="">All</option>
                {VERIFICATIONS.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </label>
          )}

          {canVerify && (
            <div className="alert-bulk-actions">
              <button type="button" disabled={busy || countEligible("verify") === 0} onClick={() => bulk("verify")}>
                Verify selected
              </button>
              <button type="button" disabled={busy || countEligible("dismiss") === 0} onClick={() => bulk("dismiss")}>
                Dismiss selected
              </button>
            </div>
          )}
          {canAct && (
            <div className="alert-bulk-actions">
              <button type="button" disabled={busy || countEligible("acknowledge") === 0} onClick={() => bulk("acknowledge")}>
                Acknowledge selected
              </button>
            </div>
          )}
        </div>

        {error && <p className="error">{error}</p>}
        {rows && rows.length === 0 && <EmptyState>No incidents match these filters.</EmptyState>}

        {rows && rows.length > 0 && (
          <table className="alert-table">
            <thead>
              <tr>
                {hasCheckboxes && (
                  <th className="alert-table-checkbox-cell">
                    <input
                      type="checkbox"
                      checked={selected.size === rows.length}
                      onChange={() => setSelected(selected.size === rows.length ? new Set() : new Set(rows.map((i) => i.id)))}
                      aria-label="Select all incidents"
                    />
                  </th>
                )}
                <th>Severity</th>
                <th>Catchment</th>
                <th>Days</th>
                <th>Peak score</th>
                <th>Verification</th>
                <th>Status</th>
                <th>Responses</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {rows.map((incident) => (
                <Fragment key={incident.id}>
                  <tr>
                    {hasCheckboxes && (
                      <td className="alert-table-checkbox-cell">
                        <input
                          type="checkbox"
                          checked={selected.has(incident.id)}
                          onChange={() => toggleSelected(incident.id)}
                          aria-label={`Select incident ${incident.id}`}
                        />
                      </td>
                    )}
                    <td>
                      <StatusChip role={severityRole(incident.severity)} label={incident.severity} />
                      {confirmationTag(incident) && (
                        <span className="alert-confirmation">
                          <StatusChip {...confirmationTag(incident)} />
                        </span>
                      )}
                    </td>
                    <td>
                      {incident.catchment}
                      {incident.wards?.length > 0 && <span className="alert-wards">{formatWards(incident.wards)}</span>}
                    </td>
                    <td className="figure">
                      {formatSpan(incident)}
                      <span className="alert-raised">
                        {incident.flagged_days} flagged day{incident.flagged_days === 1 ? "" : "s"},{" "}
                        {raisedAfter(incident.start_day, incident.created_at)}
                      </span>
                    </td>
                    <td className="figure">{incident.max_score.toFixed(3)}</td>
                    <td>
                      <StatusChip role={verificationRole(incident.verification)} label={incident.verification} />
                    </td>
                    <td>
                      <StatusChip role={alertStatusRole(incident)} label={incident.status} />
                      {incident.outcome && incident.outcome !== "not_checked" && (
                        <span className="alert-table-by">
                          {incident.outcome === "flooding_observed" ? "flooding found" : "no flooding found"}
                        </span>
                      )}
                    </td>
                    <td className="figure">{incident.responses}</td>
                    <td>
                      <button
                        type="button"
                        className="alert-responses-toggle"
                        aria-expanded={openId === incident.id}
                        onClick={() => setOpenId((id) => (id === incident.id ? null : incident.id))}
                      >
                        {openId === incident.id ? "Close" : "Open"}
                      </button>
                    </td>
                  </tr>
                  {openId === incident.id && (
                    <tr className="alert-responses-row">
                      <td colSpan={columns}>
                        <IncidentDetail id={incident.id} role={role} onChanged={() => setRefresh((n) => n + 1)} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {openId && rows && !rows.some((i) => i.id === openId) && (
        <div className="panel">
          <h2 className="panel-title">Incident {openId}</h2>
          <IncidentDetail id={openId} role={role} onChanged={() => setRefresh((n) => n + 1)} />
        </div>
      )}

      {rows && rows.length > 0 && (
        <div className="alert-list-footer">
          <span className="alert-list-footer-note">Showing {rows.length} incidents. Filter to narrow the list.</span>
          {canLoadMore && (
            <button type="button" onClick={() => setVisibleLimit((n) => Math.min(n + PAGE_SIZE, MAX_LIMIT))}>
              Load more
            </button>
          )}
        </div>
      )}
    </section>
  );
}
