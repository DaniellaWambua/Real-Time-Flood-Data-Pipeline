import { useOutletContext } from "react-router-dom";
import PageHeader from "../components/PageHeader";
import StatusChip from "../components/StatusChip";
import { roleLabel } from "../roleLabel";
import "./RoleSwitcher.css";

// The four roles are real accounts: which screens each one reaches is
// decided in one place, roleAccess.js's ROUTE_ROLES, applied both by
// Layout.jsx (hides the link) and App.jsx (redirects away even if the
// URL is typed directly). Admin's own endpoints (users, logs, pipeline
// stats) are separately enforced server-side too (backend/config.py's
// ROLES, checked by routes_dashboard.py's role_required), since those
// carry real account data; the other screens differ only in which
// workflow each role is presented, not in redacting shared sensor/
// alert data the Main Dashboard already summarises for everyone. This
// page is a reference showing what each role can see today, plus the
// one genuine way to view another role's screens: sign out and sign
// back in as that account.
const ROLES = [
  {
    role: "system_administrator",
    description:
      "The only role with access to Administration: user management, pipeline health, and system logs. Also sees every other screen except Notifications.",
  },
  {
    role: "disaster_management_agency",
    description:
      "Overview, Data stream, LSTM Anomaly, Incidents and Notifications - monitors the readings and the model, and verifies or dismisses each new incident before the field is told.",
  },
  {
    role: "emergency_responder",
    description:
      "Overview, Incidents and Notifications - sees verified incidents, acknowledges and resolves them saying whether flooding was found, and records field updates and recovery work.",
  },
  {
    role: "government_official",
    description:
      "Overview, Incidents and Notifications - sees verified incidents in high-risk areas and records the resources allocated to each, and recovery work.",
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
