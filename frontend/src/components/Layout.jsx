import { NavLink, Outlet } from "react-router-dom";
import { logout } from "../api";
import "./Layout.css";

// Four screens matching the proposal's wireframes (3.4.6). Admin is
// only linked for a system_administrator, same restriction routes_
// dashboard.py already enforces server-side on /api/users, this just
// avoids showing a link that would 403 for anyone else.
const NAV_ITEMS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/data-stream", label: "Data stream" },
  { to: "/alerts", label: "Alerts" },
  { to: "/admin", label: "Administration", adminOnly: true },
];

export default function Layout({ user, onLoggedOut }) {
  async function handleLogout() {
    await logout().catch(() => {});
    onLoggedOut();
  }

  const items = NAV_ITEMS.filter(
    (item) => !item.adminOnly || user.role === "system_administrator",
  );

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-title">Flood Risk Dashboard</div>
        <nav className="app-nav">
          {items.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="app-session">
          <span>
            {user.username} <span className="app-role">({user.role})</span>
          </span>
          <button onClick={handleLogout}>Sign out</button>
        </div>
      </header>
      <main className="app-main">
        <Outlet context={{ user }} />
      </main>
    </div>
  );
}
