import { useEffect, useRef, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./App.css";
import { login, loginWithGoogle, me } from "./api";
import { canAccess } from "./roleAccess";
import Layout from "./components/Layout";
import Footer from "./components/Footer";
import { IconBell } from "./components/icons";
import Dashboard from "./pages/Dashboard";
import DataStream from "./pages/DataStream";
import LstmAnomaly from "./pages/LstmAnomaly";
import RoleSwitcher from "./pages/RoleSwitcher";
import Incidents from "./pages/Incidents";
import Notifications from "./pages/Notifications";
import Admin from "./pages/Admin";
import SetPassword from "./pages/SetPassword";
import SecondFactor from "./components/SecondFactor";

// With no client ID configured the Google button is not shown.
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || "";

function LoginForm({ onLoggedIn }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  // "credentials", then "verify" (enter the 2FA code) or "setup" (set up 2FA first)
  const [step, setStep] = useState("credentials");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const googleButtonRef = useRef(null);

  // Password and Google sign-in both lead to the second step: a code, or setting up 2FA
  function handleLoginResult(result) {
    if (result.requires_totp) setStep("verify");
    else if (result.requires_totp_setup) setStep("setup");
    else onLoggedIn(result);
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

  // The Google script loads separately and may never load offline, so poll briefly for it.
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || step !== "credentials") {
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
  }, [step]);

  async function handlePasswordSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const result = await login(username, password);
      // With two-factor authentication on, this asks for the authenticator code first.
      handleLoginResult(result);
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
        {step === "credentials" ? (
          <form className="login-form panel" onSubmit={handlePasswordSubmit}>
            <h1>Sign in</h1>
            <p className="subtitle">Use the account your administrator invited you to.</p>

            <label>
              Username or email
              <input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
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
                {/* Google renders its button here once its script has loaded */}
                <div ref={googleButtonRef} className="google-signin-button" />
              </>
            )}
          </form>
        ) : (
          <SecondFactor mode={step} onDone={onLoggedIn} />
        )}
      </main>
      <Footer />
    </div>
  );
}

// An invite or password-reset email links to /account/<code>, shown before any sign-in
const ACCOUNT_LINK = window.location.pathname.match(/^\/account\/([^/]+)$/);

export default function App() {
  const [user, setUser] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [accountCode, setAccountCode] = useState(ACCOUNT_LINK ? ACCOUNT_LINK[1] : null);

  // On load, ask the backend if there's already a valid session cookie
  // (e.g. the page was refreshed), rather than always starting logged out.
  useEffect(() => {
    me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setCheckingSession(false));
  }, []);

  function leaveAccountPage() {
    window.history.replaceState(null, "", "/");
    setAccountCode(null);
  }

  if (accountCode) {
    return (
      <SetPassword
        code={accountCode}
        onSignedIn={(signedIn) => {
          leaveAccountPage();
          setUser(signedIn);
        }}
        onDone={leaveAccountPage}
      />
    );
  }

  if (checkingSession) {
    return <p className="subtitle centered">Checking session...</p>;
  }

  if (!user) {
    return <LoginForm onLoggedIn={setUser} />;
  }

  // Each restricted screen checks access itself, so a hidden URL cannot be opened directly.
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
          <Route path="incidents" element={guarded("/incidents", <Incidents />)} />
          <Route path="alerts" element={<Navigate to="/incidents" replace />} />
          <Route path="notifications" element={guarded("/notifications", <Notifications />)} />
          <Route path="admin" element={guarded("/admin", <Admin />)} />
          <Route path="role-switcher" element={<RoleSwitcher />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
