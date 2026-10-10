import { useEffect, useState } from "react";
import "./App.css";
import { get, login, logout, me } from "./api";

// Endpoints the dashboard API currently serves (backend/routes_dashboard.py).
// "Users" is listed last and only shown to a system_administrator, since
// that one endpoint is role-restricted rather than just login-required.
const ENDPOINTS = [
  { key: "catchments", label: "Catchments", path: "/api/catchments" },
  { key: "readings", label: "Recent readings", path: "/api/readings/recent" },
  { key: "alerts", label: "Alerts", path: "/api/alerts" },
  { key: "anomalies", label: "Recent anomalies", path: "/api/anomalies/recent" },
  { key: "sources", label: "Sources", path: "/api/sources" },
  { key: "users", label: "Users", path: "/api/users", adminOnly: true },
];

function LoginForm({ onLoggedIn }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const user = await login(username, password);
      onLoggedIn(user);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="login-form" onSubmit={handleSubmit}>
      <h1>Flood Risk Dashboard</h1>
      <p className="subtitle">Sign in with a user created via backend/create_user.py.</p>

      <label>
        Username
        <input
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          autoFocus
          required
        />
      </label>

      <label>
        Password
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
      </label>

      {error && <p className="error">{error}</p>}

      <button type="submit" disabled={submitting}>
        {submitting ? "Signing in..." : "Sign in"}
      </button>
    </form>
  );
}

function DataExplorer({ user, onLoggedOut }) {
  const [activeKey, setActiveKey] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const visibleEndpoints = ENDPOINTS.filter(
    (endpoint) => !endpoint.adminOnly || user.role === "system_administrator",
  );

  async function loadEndpoint(endpoint) {
    setActiveKey(endpoint.key);
    setLoading(true);
    setError(null);
    try {
      const result = await get(endpoint.path);
      setData(result);
    } catch (err) {
      setData(null);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleLogout() {
    await logout().catch(() => {});
    onLoggedOut();
  }

  return (
    <div className="explorer">
      <header>
        <div>
          Signed in as <strong>{user.username}</strong> ({user.role})
        </div>
        <button onClick={handleLogout}>Sign out</button>
      </header>

      <nav>
        {visibleEndpoints.map((endpoint) => (
          <button
            key={endpoint.key}
            className={endpoint.key === activeKey ? "active" : ""}
            onClick={() => loadEndpoint(endpoint)}
          >
            {endpoint.label}
          </button>
        ))}
      </nav>

      <section className="result">
        {loading && <p>Loading...</p>}
        {error && <p className="error">{error}</p>}
        {!loading && !error && data && <pre>{JSON.stringify(data, null, 2)}</pre>}
        {!loading && !error && !data && (
          <p className="subtitle">Pick an endpoint above to see its raw response.</p>
        )}
      </section>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);

  // On load, ask the backend if there's already a valid session cookie
  // (e.g. the page was refreshed), rather than always starting logged out.
  useEffect(() => {
    me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setCheckingSession(false));
  }, []);

  if (checkingSession) {
    return <p className="subtitle centered">Checking session...</p>;
  }

  return user ? (
    <DataExplorer user={user} onLoggedOut={() => setUser(null)} />
  ) : (
    <LoginForm onLoggedIn={setUser} />
  );
}
