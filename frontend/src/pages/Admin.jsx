import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import StatusChip from "../components/StatusChip";
import { connectionRole } from "../statusRoles";
import EmptyState from "../components/EmptyState";
import { get } from "../api";
import "./Admin.css";

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

  return (
    <table className="admin-table">
      <thead>
        <tr>
          <th>Source</th>
          <th>Type</th>
          <th>Status</th>
          <th>Added</th>
        </tr>
      </thead>
      <tbody>
        {sources.map((source) => (
          <tr key={source.id}>
            <td>{source.name}</td>
            <td>{source.source_type}</td>
            <td>
              <StatusChip
                role={connectionRole(source.connection_status)}
                label={source.connection_status}
              />
            </td>
            <td>{new Date(source.created_at).toLocaleDateString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function UsersPanel() {
  const [users, setUsers] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    get("/api/users")
      .then(setUsers)
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!users) return null;

  return (
    <table className="admin-table">
      <thead>
        <tr>
          <th>Username</th>
          <th>Role</th>
          <th>Created</th>
        </tr>
      </thead>
      <tbody>
        {users.map((user) => (
          <tr key={user.id}>
            <td>{user.username}</td>
            <td>{user.role}</td>
            <td>{new Date(user.created_at).toLocaleDateString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
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
      <h1>System administration</h1>

      <h2>Pipeline status</h2>
      <SourcesPanel />

      <h2>User management</h2>
      <UsersPanel />

      {/* Logs are a later addition, see routes_dashboard.py's own comment
          on list_sources being "a minimal first version". */}
    </section>
  );
}
