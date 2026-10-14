import { useOutletContext } from "react-router-dom";
import PageHeader from "../components/PageHeader";
import StatusChip from "../components/StatusChip";
import { roleLabel } from "../roleLabel";
import "./RoleSwitcher.css";

// The four roles are real accounts enforced server-side (backend/
// config.py's ROLES, checked by routes_auth.py/routes_dashboard.py's
// role_required), not a client-side toggle: this page can't actually
// make the dashboard show you another role's restricted data without
// a real session for that role, since every restricted endpoint
// re-checks the session on the server regardless of what the
// frontend displays. So rather than faking that with a client-side
// switch (which would either lie about what's restricted or do
// nothing real), this is a reference showing what each role can see
// here today, plus the one genuine way to view it: sign out and sign
// back in as a different account.
const ROLES = [
  {
    role: "system_administrator",
    description:
      "The only role with access to Administration: user management, pipeline health, and system logs. Also sees every other screen.",
  },
  {
    role: "disaster_management_agency",
    description: "Overview, Data stream, Alerts and LSTM Anomaly - the same monitoring screens every non-admin role sees.",
  },
  {
    role: "emergency_responder",
    description: "Overview, Data stream, Alerts and LSTM Anomaly - the same monitoring screens every non-admin role sees.",
  },
  {
    role: "government_official",
    description: "Overview, Data stream, Alerts and LSTM Anomaly - the same monitoring screens every non-admin role sees.",
  },
];

export default function RoleSwitcher() {
  const { user } = useOutletContext();

  return (
    <section>
      <PageHeader
        title="Role switcher"
        subtitle="What each role can see in this dashboard today"
      />

      <div className="panel role-switcher-current">
        <span className="panel-caption">Signed in as</span>
        <div className="role-switcher-current-row">
          <strong>{user.username}</strong>
          <StatusChip role="active" label={roleLabel(user.role)} />
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Roles (proposal 3.6.2, Chapter 3 use case diagram)</h2>
        </div>

        <ul className="role-switcher-list">
          {ROLES.map((item) => (
            <li key={item.role} className="role-switcher-item">
              <div className="role-switcher-item-header">
                <StatusChip
                  role={item.role === user.role ? "active" : "muted"}
                  label={roleLabel(item.role)}
                />
                {item.role === user.role && <span className="role-switcher-you">You</span>}
              </div>
              <p className="role-switcher-item-description">{item.description}</p>
            </li>
          ))}
        </ul>

        <p className="role-switcher-note">
          Access is enforced by the backend session, not by this page, so viewing another role's
          screens for real means signing out and signing back in with that role's account (the
          &ldquo;Sign out&rdquo; control at the bottom of the sidebar).
        </p>
      </div>
    </section>
  );
}
