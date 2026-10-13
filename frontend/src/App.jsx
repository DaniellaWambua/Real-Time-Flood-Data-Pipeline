import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./App.css";
import { login, me } from "./api";
import Layout from "./components/Layout";
import Footer from "./components/Footer";
import { IconBell } from "./components/icons";
import Dashboard from "./pages/Dashboard";
import DataStream from "./pages/DataStream";
import Alerts from "./pages/Alerts";
import Admin from "./pages/Admin";

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
    <div className="auth-shell">
      <header className="auth-header">
        <div className="auth-brand">
          <span className="auth-brand-mark" aria-hidden="true">
            <IconBell />
          </span>
          <div className="auth-brand-text">
            <span className="auth-brand-title">Flood Early Warning</span>
            <span className="auth-brand-tagline">Nairobi river catchments</span>
          </div>
        </div>
      </header>
      <main className="auth-main">
        <form className="login-form panel" onSubmit={handleSubmit}>
          <h1>Sign in</h1>
          <p className="subtitle">Use an account created via backend/create_user.py.</p>

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
      </main>
      <Footer />
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

  if (!user) {
    return <LoginForm onLoggedIn={setUser} />;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout user={user} onLoggedOut={() => setUser(null)} />}>
          <Route index element={<Dashboard />} />
          <Route path="data-stream" element={<DataStream />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="admin" element={<Admin />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
