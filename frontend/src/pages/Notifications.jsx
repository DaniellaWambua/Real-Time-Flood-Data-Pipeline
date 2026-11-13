import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import StatusChip from "../components/StatusChip";
import { get, post } from "../api";
import { pushState, turnPushOff, turnPushOn } from "../push";
import "./Notifications.css";

// The user's notifications (backend/notify.py). Opening one marks it read and goes to the incident.
// Push notifications can be turned on here once the app is installed.
const KIND = {
  verify: { role: "warning", label: "to verify" },
  incident: { role: "critical", label: "incident" },
  update: { role: "active", label: "update" },
  rain: { role: "warning", label: "rain forecast" },
};

const PUSH_TEXT = {
  on: "Notifications are pushed to this device, even when the app is closed.",
  off: "Turn this on to get notifications on this device even when the app is closed.",
  blocked: "Notifications are blocked for this site in the browser settings.",
  unavailable: "Push notifications are not available here: install the app on a supported browser, or ask the administrator to set them up on the server.",
};

export default function Notifications() {
  const navigate = useNavigate();
  const [rows, setRows] = useState(null);
  const [onlyUnread, setOnlyUnread] = useState(false);
  const [push, setPush] = useState(null);
  const [error, setError] = useState(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    get("/api/notifications", { unread: onlyUnread ? "true" : "", limit: 100 })
      .then(setRows)
      .catch((err) => setError(err.message));
  }, [onlyUnread, refresh]);

  useEffect(() => {
    pushState().then(setPush).catch(() => setPush("unavailable"));
  }, []);

  async function open(n) {
    if (!n.read_at) await post(`/api/notifications/${n.id}/read`, {}).catch(() => {});
    window.dispatchEvent(new Event("notifications-changed"));
    if (n.link) navigate(n.link);
    else setRefresh((x) => x + 1);
  }

  async function readAll() {
    await post("/api/notifications/read-all", {}).catch((err) => setError(err.message));
    window.dispatchEvent(new Event("notifications-changed"));
    setRefresh((x) => x + 1);
  }

  async function togglePush() {
    try {
      if (push === "on") await turnPushOff();
      else await turnPushOn();
      setPush(await pushState());
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }

  const unread = (rows ?? []).filter((n) => !n.read_at).length;

  return (
    <section>
      <PageHeader title="Notifications" subtitle="Incidents, model updates and rain forecasts that need your attention" />

      <div className="panel notifications-push">
        <p>{push ? PUSH_TEXT[push] : "Checking this device..."}</p>
        {(push === "on" || push === "off") && (
          <button type="button" onClick={togglePush}>
            {push === "on" ? "Turn off on this device" : "Turn on for this device"}
          </button>
        )}
      </div>

      <div className="panel">
        <div className="notifications-toolbar">
          <label>
            <input type="checkbox" checked={onlyUnread} onChange={(e) => setOnlyUnread(e.target.checked)} /> Unread only
          </label>
          <button type="button" disabled={unread === 0} onClick={readAll}>
            Mark all read
          </button>
        </div>
        {error && <p className="error">{error}</p>}
        {rows && rows.length === 0 && <EmptyState>No notifications.</EmptyState>}
        {rows && rows.length > 0 && (
          <ul className="notifications-list">
            {rows.map((n) => (
              <li key={n.id} className={n.read_at ? "" : "notifications-unread"}>
                <button type="button" className="notifications-item" onClick={() => open(n)}>
                  <span className="notifications-kind">
                    <StatusChip {...(KIND[n.kind] ?? { role: "muted", label: n.kind })} />
                  </span>
                  <span className="notifications-text">
                    <strong>{n.title}</strong>
                    <span>{n.body}</span>
                  </span>
                  <span className="notifications-time">{new Date(n.created_at).toLocaleString()}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
