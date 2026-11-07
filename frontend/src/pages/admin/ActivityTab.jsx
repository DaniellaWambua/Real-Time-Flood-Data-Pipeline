import { useEffect, useState } from "react";
import { IconDocument } from "../../components/icons";
import { get } from "../../api";

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
  user_invited: "Invited user",
  user_invite_resent: "Resent invite",
  user_activated: "Activated account",
  user_details_changed: "Edited user details",
  password_reset_sent: "Sent password reset link",
  password_reset_completed: "Reset own password",
  login_password_ok_awaiting_totp: "Password accepted, awaiting 2FA code",
  totp_enabled: "Turned on two-factor sign-in",
  totp_disabled: "Turned off two-factor sign-in",
  alert_acknowledged: "Acknowledged alert",
  alert_resolved: "Resolved alert",
  reading_rejected: "Rejected a reading",
  login_password_ok_awaiting_2fa_setup: "Password accepted, setting up 2FA",
  user_2fa_reset: "Reset a user's two-factor sign-in",
  user_email_changed: "Changed a user's email",
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

// Administration's Activity log tab. To be split by area in the next step.
export default function ActivityTab() {
  return (
    <div className="admin-panel-stack">
      <LogsPanel />
    </div>
  );
}
