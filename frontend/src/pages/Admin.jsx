import { useEffect, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import StatusChip from "../components/StatusChip";
import MetricCard from "../components/MetricCard";
import PageHeader from "../components/PageHeader";
import { IconDocument } from "../components/icons";
import { connectionRole } from "../statusRoles";
import { roleLabel } from "../roleLabel";
import EmptyState from "../components/EmptyState";
import { get, post, patch } from "../api";
import "./Admin.css";

// Matches backend/config.py's ROLES (Chapter 3's use case diagram
// actors). Kept here rather than fetched, since the four roles are
// fixed by that diagram, not data.
const ROLES = [
  "disaster_management_agency",
  "emergency_responder",
  "government_official",
  "system_administrator",
];

// GET /api/admin/stats and the card order on the reference layout,
// not the chapter 3 glossary order: alerts before anomaly results,
// since there IS alert data but there isn't yet a live anomaly score
// (see the "Not scoring" badge below).
function StatsRow({ stats }) {
  return (
    <div className="metric-card-row admin-metric-row">
      <MetricCard label="Users" value={stats.users} />
      <MetricCard label="Catchments" value={stats.catchments} />
      <MetricCard label="Data sources" value={stats.data_sources} />
      <MetricCard label="Readings" value={stats.readings.toLocaleString()} />
      <MetricCard label="Alerts" value={stats.alerts.toLocaleString()} />
      <MetricCard
        label="Anomaly results"
        value={stats.anomalies}
        badge={{ role: "muted", glyph: "○", label: "Not scoring" }}
      />
    </div>
  );
}

// GET /api/alerts/summary and /api/alerts/trend taught the same lesson
// here: a database overview is a glance, not a page of its own, so
// this reads one small endpoint rather than totalling up what the
// other panels already fetched.
function StatsPanel() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    get("/api/admin/stats")
      .then(setStats)
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!stats) return null;

  return <StatsRow stats={stats} />;
}

// GET /api/sources has no matching PATCH (it is historical replay
// data, see routes_dashboard.py's list_sources()), so, same as
// Alerts.jsx's read-only table, there is nothing real for a
// "Reconnect" button to do yet and one is not added here - only
// "View stream" is a genuine link, to the Data stream page this data
// actually feeds.
function SourcesPanel() {
  const [sources, setSources] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    get("/api/sources")
      .then(setSources)
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!sources) return null;

  const connectedCount = sources.filter((s) => s.connection_status === "connected").length;

  return (
    <div className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Data sources</h2>
        <span className="panel-caption">
          {connectedCount} of {sources.length} connected
        </span>
      </div>

      {/* A glanceable status grid above the detail table, per
          Daniella's request for something closer to how Kubernetes
          shows node/pod health - one small tile per source with its
          live connection status up front, rather than only a text
          row buried in a wider table. Same /api/sources data as the
          table below, not a second fetch or a separate concept. */}
      <div className="pipeline-health-grid">
        {sources.map((source) => (
          <div key={source.id} className="pipeline-health-tile">
            <div className="pipeline-health-tile-header">
              <span
                className={`pipeline-health-dot pipeline-health-dot--${connectionRole(source.connection_status)}`}
                aria-hidden="true"
              />
              <span className="pipeline-health-tile-name">{source.name}</span>
            </div>
            <StatusChip role={connectionRole(source.connection_status)} label={source.connection_status} />
            <dl className="pipeline-health-tile-stats">
              <div>
                <dt>Last ingested</dt>
                <dd className="figure">
                  {source.last_ingested_at ? new Date(source.last_ingested_at).toLocaleString() : "No data yet"}
                </dd>
              </div>
              <div>
                <dt>Records</dt>
                <dd className="figure">{source.record_count.toLocaleString()}</dd>
              </div>
            </dl>
          </div>
        ))}
      </div>

      <table className="admin-table">
        <thead>
          <tr>
            <th>Source</th>
            <th>Type</th>
            <th>Status</th>
            <th>Last ingested</th>
            <th>Records</th>
            <th>Added</th>
            <th aria-hidden="true" />
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.id}>
              <td className="admin-table-strong">{source.name}</td>
              <td>{source.source_type}</td>
              <td>
                <StatusChip
                  role={connectionRole(source.connection_status)}
                  label={source.connection_status}
                />
              </td>
              {/* This is historical replay data, not a live feed (see
                  routes_dashboard.py's list_sources()), so this is a
                  record of when ingestion last actually happened, not a
                  real-time freshness check against wall-clock time. */}
              <td className="figure">
                {source.last_ingested_at
                  ? new Date(source.last_ingested_at).toLocaleString()
                  : "No data yet"}
              </td>
              <td className="figure">{source.record_count.toLocaleString()}</td>
              <td className="figure">{new Date(source.created_at).toLocaleDateString()}</td>
              <td className="admin-table-link-cell">
                {source.connection_status === "connected" ? (
                  <Link to="/data-stream" className="admin-stream-link">
                    View stream
                  </Link>
                ) : (
                  // Visual-only, matching the Alerts page's Acknowledge/
                  // Resolve precedent: GET /api/sources has no matching
                  // PATCH, so there is nothing real behind a reconnect
                  // action yet. Shown disabled with an explanatory title
                  // rather than left out, since the reference layout
                  // always shows one of these two controls per row.
                  <button
                    type="button"
                    className="admin-reconnect-button"
                    disabled
                    title="Not available yet - this data source has no live reconnect endpoint"
                  >
                    Reconnect
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function NewUserForm({ onCreated }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState(ROLES[0]);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    post("/api/users", { username, password, role })
      .then((user) => {
        onCreated(user);
        setUsername("");
        setPassword("");
        setRole(ROLES[0]);
      })
      .catch((err) => setError(err.message))
      .finally(() => setSubmitting(false));
  }

  return (
    <form className="admin-new-user" onSubmit={handleSubmit}>
      <label className="admin-new-user-field">
        Username
        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
      </label>

      <label className="admin-new-user-field">
        Temporary password
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          minLength={8}
          required
        />
      </label>

      <label className="admin-new-user-field">
        Role
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {roleLabel(r)}
            </option>
          ))}
        </select>
      </label>

      <button type="submit" disabled={submitting} className="admin-new-user-submit">
        {submitting ? "Adding..." : "Add user"}
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}

function UserRow({ user, currentUserId, onChange }) {
  const [resetting, setResetting] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const isSelf = user.id === currentUserId;

  function applyPatch(body) {
    setBusy(true);
    setError(null);
    patch(`/api/users/${user.id}`, body)
      .then((updated) => {
        onChange(updated);
        setResetting(false);
        setNewPassword("");
      })
      .catch((err) => setError(err.message))
      .finally(() => setBusy(false));
  }

  return (
    <>
      <tr>
        <td className="admin-table-strong">
          {user.username}
          {isSelf && <span className="admin-you-badge">You</span>}
        </td>
        <td>
          <select
            value={user.role}
            disabled={busy}
            onChange={(e) => applyPatch({ role: e.target.value })}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {roleLabel(r)}
              </option>
            ))}
          </select>
        </td>
        <td>
          <StatusChip
            role={user.is_active ? "good" : "muted"}
            label={user.is_active ? "active" : "deactivated"}
          />
        </td>
        <td className="figure">{new Date(user.created_at).toLocaleDateString()}</td>
        <td className="admin-table-actions">
          <button
            type="button"
            disabled={busy || isSelf}
            title={isSelf ? "You cannot deactivate your own account" : undefined}
            onClick={() => applyPatch({ is_active: !user.is_active })}
          >
            {user.is_active ? "Deactivate" : "Reactivate"}
          </button>
          <button type="button" disabled={busy} onClick={() => setResetting((v) => !v)}>
            Reset password
          </button>
        </td>
      </tr>

      {resetting && (
        <tr>
          <td colSpan={5}>
            <form
              className="admin-reset-password"
              onSubmit={(event) => {
                event.preventDefault();
                applyPatch({ password: newPassword });
              }}
            >
              <input
                type="password"
                placeholder="New password (min. 8 characters)"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                minLength={8}
                required
              />
              <button type="submit" disabled={busy}>
                Set password
              </button>
              <button type="button" onClick={() => setResetting(false)}>
                Cancel
              </button>
            </form>
          </td>
        </tr>
      )}

      {error && (
        <tr>
          <td colSpan={5} className="error">
            {error}
          </td>
        </tr>
      )}
    </>
  );
}

function UsersPanel({ currentUserId }) {
  const [users, setUsers] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    get("/api/users")
      .then(setUsers)
      .catch((err) => setError(err.message));
  }, []);

  function handleCreated(user) {
    setUsers((current) =>
      [...(current ?? []), user].sort((a, b) => a.username.localeCompare(b.username)),
    );
  }

  function handleChanged(updated) {
    setUsers((current) =>
      (current ?? []).map((u) => (u.id === updated.id ? { ...u, ...updated } : u)),
    );
  }

  if (error) return <p className="error">{error}</p>;

  return (
    <div className="panel">
      <div className="panel-header">
        <h2 className="panel-title">User management</h2>
        {users && (
          <span className="panel-caption">
            {users.length} user{users.length === 1 ? "" : "s"}
          </span>
        )}
      </div>

      <NewUserForm onCreated={handleCreated} />

      {users && (
        <table className="admin-table">
          <thead>
            <tr>
              <th>Username</th>
              <th>Role</th>
              <th>Status</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <UserRow
                key={user.id}
                user={user}
                currentUserId={currentUserId}
                onChange={handleChanged}
              />
            ))}
          </tbody>
        </table>
      )}

      {currentUserId && (
        <p className="admin-panel-note">
          You cannot deactivate the account you are signed in with.
        </p>
      )}
    </div>
  );
}

// Human-readable labels for system_logs.action (backend/models.py's
// log_event callers). Falls back to the raw action string for
// anything not listed here, so a future event type still shows up
// rather than disappearing.
const ACTION_LABELS = {
  login_success: "Signed in",
  login_failure: "Failed sign-in attempt",
  user_created: "Created user",
  user_role_changed: "Changed role",
  user_password_reset: "Reset password",
  user_deactivated: "Deactivated user",
  user_reactivated: "Reactivated user",
};

function LogsPanel() {
  const [logs, setLogs] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Capped server-side (GET /api/logs defaults to 20) for the same
    // reason the alert management screen's own table is: a fixed
    // recent window, not an endless scroll.
    get("/api/logs")
      .then(setLogs)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <div className="panel">
      <div className="panel-header">
        <h2 className="panel-title">System logs</h2>
      </div>

      {error && <p className="error">{error}</p>}

      {logs && logs.length === 0 && (
        <div className="admin-logs-empty">
          <IconDocument className="admin-logs-empty-icon" />
          <div>
            <p className="admin-logs-empty-title">No system events logged yet</p>
            <p className="admin-logs-empty-caption">
              Source connections, user changes and alert activity will be listed here.
            </p>
          </div>
        </div>
      )}

      {logs && logs.length > 0 && (
        <table className="admin-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>User</th>
              <th>Event</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id}>
                <td className="figure">{new Date(log.occurred_at).toLocaleString()}</td>
                <td>{log.actor ?? "—"}</td>
                <td>{ACTION_LABELS[log.action] ?? log.action}</td>
                <td>{log.detail ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function Admin() {
  const { user } = useOutletContext();

  // The nav link is already hidden for a non-admin (components/Layout.jsx),
  // but a direct URL visit bypasses that, so this is a second, real gate,
  // matching the server-side role_required("system_administrator") on
  // /api/users rather than trusting the client alone.
  if (user.role !== "system_administrator") {
    return (
      <EmptyState>
        System administration is restricted to the system_administrator
        role. You are signed in as {user.role}.
      </EmptyState>
    );
  }

  return (
    <section>
      <PageHeader title="Administration" subtitle="System health, data sources and user access" />

      <StatsPanel />

      <div className="admin-panel-stack">
        <SourcesPanel />
        <UsersPanel currentUserId={user.id} />
        <LogsPanel />
      </div>
    </section>
  );
}
