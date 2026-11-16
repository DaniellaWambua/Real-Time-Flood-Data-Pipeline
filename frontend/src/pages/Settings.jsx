import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import PageHeader from "../components/PageHeader";
import PasswordStrength from "../components/PasswordStrength";
import { IconBellOutline, IconKey, IconScreens, IconShield } from "../components/icons";
import { get, post } from "../api";
import { canAccess, SCREENS } from "../roleAccess";
import { ROLE_OPTIONS, roleLabel } from "../roleLabel";
import { pushState, turnPushOff, turnPushOn } from "../push";
import "./Settings.css";

// Who you are at the top, then one card per task: password, two-factor sign-in, how you are
// reached, and what your role can do.
const TOLD_ABOUT = {
  disaster_management_agency: "New incidents to verify, model updates and heavy-rain forecasts",
  emergency_responder: "Verified incidents, model updates and heavy-rain forecasts",
  government_official: "Verified incidents, model updates and heavy-rain forecasts",
};

const PUSH_STATE = {
  on: "on for this device",
  off: "off on this device",
  blocked: "blocked in this browser's settings",
  unavailable: "not available on this browser",
};

function formatDate(iso) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

function sinceText(iso) {
  if (!iso) return "Not changed since your account was set up";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (days < 1) return "Changed today";
  if (days === 1) return "Changed yesterday";
  if (days < 60) return `Changed ${days} days ago`;
  return `Changed on ${formatDate(iso)}`;
}

function initials(account) {
  const source = account.full_name || account.username;
  return source
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");
}

function Identity({ account }) {
  const details = [account.username, account.organisation, account.email].filter(Boolean);
  return (
    <div className="panel settings-identity">
      <span className="settings-avatar" aria-hidden="true">
        {initials(account)}
      </span>
      <div className="settings-identity-text">
        <span className="settings-identity-name">{account.full_name || account.username}</span>
        <span className="settings-muted">{details.join(" · ")}</span>
        {account.created_at && (
          <span className="settings-muted">Member since {formatDate(account.created_at)}</span>
        )}
      </div>
      <span className="settings-role">{roleLabel(account.role)}</span>
    </div>
  );
}

function TaskCard({ Icon, title, status, children }) {
  return (
    <div className="panel settings-card">
      <Icon className="settings-card-icon" />
      <h2 className="settings-card-title">{title}</h2>
      <p className="settings-muted">{status}</p>
      <div className="settings-card-body">{children}</div>
    </div>
  );
}

function PasswordCard({ account, onChanged }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);
  const [strongEnough, setStrongEnough] = useState(false);

  function update(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
    setError(null);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!strongEnough) return setError("Choose a stronger new password, as the meter shows.");
    if (form.next !== form.confirm) return setError("The two new passwords don't match.");
    setSaving(true);
    try {
      await post("/account/password", { current_password: form.current, new_password: form.next });
      setForm({ current: "", next: "", confirm: "" });
      setOpen(false);
      setDone(true);
      onChanged();
    } catch (err) {
      setError(err.message.charAt(0).toUpperCase() + err.message.slice(1) + ".");
    } finally {
      setSaving(false);
    }
  }

  return (
    <TaskCard Icon={IconKey} title="Password" status={done ? "Password changed" : sinceText(account.password_changed_at)}>
      {!open ? (
        <button
          type="button"
          onClick={() => {
            setOpen(true);
            setDone(false);
          }}
        >
          Change password
        </button>
      ) : (
        <form className="settings-form" onSubmit={handleSubmit}>
          <label>
            Current password
            <input
              type="password"
              autoComplete="current-password"
              value={form.current}
              onChange={(e) => update("current", e.target.value)}
              required
            />
          </label>
          <label>
            New password
            <input
              type="password"
              autoComplete="new-password"
              value={form.next}
              onChange={(e) => update("next", e.target.value)}
              required
            />
          </label>
          <PasswordStrength
            password={form.next}
            person={{
              username: account.username,
              fullName: account.full_name,
              email: account.email,
              organisation: account.organisation,
            }}
            onChange={setStrongEnough}
          />
          <label>
            Confirm new password
            <input
              type="password"
              autoComplete="new-password"
              value={form.confirm}
              onChange={(e) => update("confirm", e.target.value)}
              required
            />
          </label>
          {error && <p className="error">{error}</p>}
          <div className="settings-form-actions">
            <button type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save password"}
            </button>
            <button type="button" className="settings-link-button" onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </TaskCard>
  );
}

function TwoFactorCard({ enabled }) {
  return (
    <TaskCard
      Icon={IconShield}
      title="Two-factor sign-in"
      status={enabled ? "On, a code from your authenticator app at every sign-in" : "Not set up yet"}
    >
      <span className={`settings-pill${enabled ? " settings-pill--good" : ""}`}>
        {enabled ? "Protected" : "Set up at your next sign-in"}
      </span>
      <p className="settings-note">Lost your phone? Ask the System Administrator to reset it.</p>
    </TaskCard>
  );
}

function NotificationsCard({ role }) {
  const [push, setPush] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    pushState().then(setPush).catch(() => setPush("unavailable"));
  }, []);

  async function toggle() {
    try {
      if (push === "on") await turnPushOff();
      else await turnPushOn();
      setPush(await pushState());
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <TaskCard Icon={IconBellOutline} title="How you'll be reached" status={TOLD_ABOUT[role]}>
      <ul className="settings-channels">
        <li>
          <span>In the app</span>
          <span className="settings-pill settings-pill--good">always</span>
        </li>
        <li>
          <span>Push</span>
          <span className={`settings-pill${push === "on" ? " settings-pill--good" : ""}`}>
            {push ? PUSH_STATE[push] : "checking..."}
          </span>
        </li>
      </ul>
      {(push === "on" || push === "off") && (
        <button type="button" onClick={toggle}>
          {push === "on" ? "Turn off on this device" : "Turn on for this device"}
        </button>
      )}
      {error && <p className="error">{error}</p>}
    </TaskCard>
  );
}

function AccessCard({ role }) {
  const [open, setOpen] = useState(false);
  const description = ROLE_OPTIONS.find((r) => r.value === role)?.description;
  const screens = SCREENS.filter((s) => canAccess(role, s.path));
  return (
    <TaskCard Icon={IconScreens} title="Your access" status={`${screens.length} screens, plus Settings`}>
      {!open ? (
        <button type="button" onClick={() => setOpen(true)}>
          See what you can do
        </button>
      ) : (
        <>
          {description && <p className="settings-note">{description}</p>}
          <ul className="settings-screens">
            {screens.map((s) => (
              <li key={s.path}>{s.label}</li>
            ))}
          </ul>
          <button type="button" className="settings-link-button" onClick={() => setOpen(false)}>
            Hide
          </button>
        </>
      )}
    </TaskCard>
  );
}

export default function Settings() {
  const { user } = useOutletContext();
  const [account, setAccount] = useState(null);
  const [error, setError] = useState(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    get("/account")
      .then(setAccount)
      .catch((err) => setError(err.message));
  }, [refresh]);

  return (
    <section>
      <PageHeader title="Settings" subtitle="Your account, how you sign in and how you are reached" />
      {error && <p className="error">{error}</p>}
      {account && (
        <>
          <Identity account={account} />
          <div className="settings-grid">
            <PasswordCard account={account} onChanged={() => setRefresh((x) => x + 1)} />
            <TwoFactorCard enabled={account.totp_enabled} />
            {canAccess(user.role, "/notifications") && <NotificationsCard role={user.role} />}
            <AccessCard role={user.role} />
          </div>
        </>
      )}
    </section>
  );
}
