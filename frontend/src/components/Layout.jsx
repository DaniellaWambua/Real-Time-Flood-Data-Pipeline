import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { logout, get, me } from "../api";
import { roleLabel } from "../roleLabel";
import { canAccess } from "../roleAccess";
import { IconGrid, IconPulse, IconBell, IconSliders, IconBrain, IconSwitch, IconInbox } from "./icons";
import Footer from "./Footer";
import "./Layout.css";

// Which of these show up in the sidebar is decided by roleAccess.js's
// ROUTE_ROLES, matching the proposal's wireframes (3.4.6): a role that
// cannot open a screen does not see it linked either, rather than
// seeing a link that leads to a redirect or a 403.
const NAV_ITEMS = [
  { to: "/", label: "Overview", end: true, Icon: IconGrid },
  { to: "/data-stream", label: "Data stream", Icon: IconPulse },
  { to: "/lstm-anomaly", label: "LSTM anomaly", Icon: IconBrain },
  { to: "/incidents", label: "Incidents", Icon: IconBell, badge: "incidents" },
  { to: "/notifications", label: "Notifications", Icon: IconInbox, badge: "unread" },
  { to: "/admin", label: "Administration", Icon: IconSliders },
  { to: "/role-switcher", label: "Role switcher", Icon: IconSwitch },
];

export default function Layout({ user, onLoggedOut }) {
  const [badges, setBadges] = useState({ incidents: 0, unread: 0 });

  // The sidebar's two badges: incidents waiting for this role (pending verification for Disaster
  // Management, active verified ones for everyone else) and unread notifications. Refreshed every
  // minute, and straight away when the Notifications screen marks something read.
  useEffect(() => {
    function load() {
      get("/api/incidents/summary")
        .then((s) => setBadges((b) => ({ ...b, incidents: user.role === "disaster_management_agency" ? s.pending : s.active })))
        .catch(() => {});
      if (canAccess(user.role, "/notifications")) {
        get("/api/notifications/unread-count")
          .then((r) => setBadges((b) => ({ ...b, unread: r.unread })))
          .catch(() => {});
      }
    }
    load();
    const timer = setInterval(load, 60000);
    window.addEventListener("notifications-changed", load);
    return () => {
      clearInterval(timer);
      window.removeEventListener("notifications-changed", load);
    };
  }, [user.role]);

  // Every tab of a browser shares one sign-in. If another tab signs in as a different
  // account, or signs out, this tab would keep showing the old role's screens while the
  // backend answers as the new one. Check whenever the tab comes back into view and reload
  // so the screens match whoever is really signed in.
  useEffect(() => {
    function checkSession() {
      if (document.visibilityState !== "visible") return;
      me()
        .then((current) => {
          if (current.username !== user.username || current.role !== user.role) window.location.reload();
        })
        // signed out elsewhere; a backend that is simply down is left alone
        .catch((err) => err.message === "not logged in" && window.location.reload());
    }
    document.addEventListener("visibilitychange", checkSession);
    window.addEventListener("focus", checkSession);
    return () => {
      document.removeEventListener("visibilitychange", checkSession);
      window.removeEventListener("focus", checkSession);
    };
  }, [user.username, user.role]);

  async function handleLogout() {
    await logout().catch(() => {});
    onLoggedOut();
  }

  const items = NAV_ITEMS.filter((item) => canAccess(user.role, item.to));

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="sidebar-brand-mark" aria-hidden="true">
            <IconBell />
          </span>
          <div className="sidebar-brand-text">
            <span className="sidebar-title">Flood Early Warning</span>
            <span className="sidebar-tagline">Nairobi river catchments</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          {items.map(({ to, label, end, Icon, badge }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `sidebar-nav-item${isActive ? " active" : ""}`}
            >
              <Icon className="sidebar-nav-icon" />
              <span className="sidebar-nav-label">{label}</span>
              {badge && badges[badge] > 0 && (
                <span className="sidebar-nav-badge">{badges[badge].toLocaleString()}</span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-user">
            <span className="sidebar-avatar" aria-hidden="true">
              {user.username.charAt(0).toUpperCase()}
            </span>
            <div className="sidebar-user-text">
              <span className="sidebar-username">{user.username}</span>
              <span className="sidebar-role">{roleLabel(user.role)}</span>
            </div>
          </div>
          <button type="button" className="sidebar-signout" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </aside>

      <div className="app-content-area">
        <main className="app-main">
          <Outlet context={{ user }} />
        </main>
        <Footer />
      </div>
    </div>
  );
}
