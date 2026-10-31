import { useEffect, useRef, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./App.css";
import { login, loginWithGoogle, me, verifyTotp } from "./api";
import { canAccess } from "./roleAccess";
import Layout from "./components/Layout";
import Footer from "./components/Footer";
import { IconBell } from "./components/icons";
import Dashboard from "./pages/Dashboard";
import DataStream from "./pages/DataStream";
import LstmAnomaly from "./pages/LstmAnomaly";
import RoleSwitcher from "./pages/RoleSwitcher";
import Alerts from "./pages/Alerts";
import Admin from "./pages/Admin";

// Set by index.html's Google Identity Services script tag. Read once
// here rather than hardcoded, so a build with no client id configured
// (e.g. VITE_GOOGLE_CLIENT_ID unset) simply never renders the button,
// instead of rendering one that would fail on every click.
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || "";

function LoginForm({ onLoggedIn }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [awaitingTotp, setAwaitingTotp] = useState(false);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const googleButtonRef = useRef(null);

  // Handles the result of either login step (password+2FA or Google)
  // the same way, since both can come back needing a TOTP code.
  function handleLoginResult(result) {
    if (result.requires_totp) {
      setAwaitingTotp(true);
    } else {
      onLoggedIn(result);
    }
  }

  async function handleGoogleCredential(response) {
    setSubmitting(true);
    setError(null);
    try {
      const result = await loginWithGoogle(response.credential);
      handleLoginResult(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  // Google Identity Services loads from index.html as a separate
  // <script>, so it may not be ready the instant this component mounts
  // (and, deliberately, this whole system still has to work with no
  // internet at all - see docs/system-overview-simple.md - so the
  // script may never load). Poll briefly for window.google and just
  // leave the button area empty if it never turns up, rather than
  // showing a button that would fail on every click.
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || awaitingTotp) {
      return;
    }
    let cancelled = false;
    let attempts = 0;

    function tryRender() {
      if (cancelled) return;
      if (window.google?.accounts?.id && googleButtonRef.current) {
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: handleGoogleCredential,
        });
        window.google.accounts.id.renderButton(googleButtonRef.current, {
          theme: "outline",
          size: "large",
          width: 300,
        });
        return;
      }
      attempts += 1;
      if (attempts < 20) {
        setTimeout(tryRender, 250);
      }
    }

    tryRender();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [awaitingTotp]);

  async function handlePasswordSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const result = await login(username, password);
      // Password was correct, but if this account has 2FA on (backend/
      // routes_auth.py's /login doesn't open a full session yet),
      // handleLoginResult asks for the authenticator code instead of
      // calling onLoggedIn straight away.
      handleLoginResult(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTotpSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const user = await verifyTotp(code);
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
        {!awaitingTotp ? (
          <form className="login-form panel" onSubmit={handlePasswordSubmit}>
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

            {GOOGLE_CLIENT_ID && (
              <>
                <p className="auth-divider">or</p>
                {/* Google Identity Services renders its own button into
                    this div once index.html's script has loaded (see
                    the effect above); left empty otherwise, e.g. with
                    no internet connection. */}
                <div ref={googleButtonRef} className="google-signin-button" />
              </>
            )}
          </form>
        ) : (
          <form className="login-form panel" onSubmit={handleTotpSubmit}>
            <h1>Enter your code</h1>
            <p className="subtitle">
              Open your authenticator app and enter the 6-digit code for this account.
            </p>

            <label>
              Authentication code
              <input
                value={code}
                onChange={(event) => setCode(event.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                required
              />
            </label>

            {error && <p className="error">{error}</p>}

            <button type="submit" disabled={submitting}>
              {submitting ? "Verifying..." : "Verify"}
            </button>
          </form>
        )}
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

  // Each restricted screen checks roleAccess.js's canAccess itself, in
  // addition to Layout.jsx hiding its nav link: that stops a role from
  // reaching a screen by typing its URL directly, not just by clicking
  // a link that was never shown. Dashboard and role-switcher are open
  // to every role, so they need no check.
  function guarded(path, element) {
    return canAccess(user.role, path) ? element : <Navigate to="/" replace />;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout user={user} onLoggedOut={() => setUser(null)} />}>
          <Route index element={<Dashboard />} />
          <Route path="data-stream" element={guarded("/data-stream", <DataStream />)} />
          <Route path="lstm-anomaly" element={guarded("/lstm-anomaly", <LstmAnomaly />)} />
          <Route path="alerts" element={guarded("/alerts", <Alerts />)} />
          <Route path="admin" element={guarded("/admin", <Admin />)} />
          <Route path="role-switcher" element={<RoleSwitcher />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
