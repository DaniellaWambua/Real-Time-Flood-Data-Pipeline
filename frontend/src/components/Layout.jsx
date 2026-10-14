import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { logout, get } from "../api";
import { roleLabel } from "../roleLabel";
import { IconGrid, IconPulse, IconBell, IconSliders, IconBrain, IconSwitch } from "./icons";
import Footer from "./Footer";
import "./Layout.css";

// Four screens matching the proposal's wireframes (3.4.6). Admin is
// only linked for a system_administrator, same restriction routes_
// dashboard.py already enforces server-side on /api/users, this just
// avoids showing a link that would 403 for anyone else.
const NAV_ITEMS = [
  { to: "/", label: "Overview", end: true, Icon: IconGrid },
  { to: "/data-stream", label: "Data stream", Icon: IconPulse },
  { to: "/lstm-anomaly", label: "LSTM anomaly", Icon: IconBrain },
  { to: "/alerts", label: "Alerts", Icon: IconBell, showAlertCount: true },
  { to: "/admin", label: "Administration", Icon: IconSliders, adminOnly: true },
  { to: "/role-switcher", label: "Role switcher", Icon: IconSwitch },
];

export default function Layout({ user, onLoggedOut }) {
  const [alertCount, setAlertCount] = useState(null);

  // One fetch for the sidebar's own Alerts badge, not re-run per page
  // visit: Layout is the layout route and stays mounted across child
  // route changes, so this effect only fires once per session rather
  // than once per navigation.
  useEffect(() => {
    get("/api/alerts/summary")
      .then((summary) => setAlertCount(summary.total))
      .catch(() => setAlertCount(null));
  }, []);

  async function handleLogout() {
    await logout().catch(() => {});
    onLoggedOut();
  }

  const items = NAV_ITEMS.filter(
    (item) => !item.adminOnly || user.role === "system_administrator",
  );

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
          {items.map(({ to, label, end, Icon, showAlertCount }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `sidebar-nav-item${isActive ? " active" : ""}`}
            >
              <Icon className="sidebar-nav-icon" />
              <span className="sidebar-nav-label">{label}</span>
              {showAlertCount && alertCount > 0 && (
                <span className="sidebar-nav-badge">{alertCount.toLocaleString()}</span>
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
