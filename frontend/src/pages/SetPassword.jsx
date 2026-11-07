import { useEffect, useState } from "react";
import Footer from "../components/Footer";
import { IconBell } from "../components/icons";
import SecondFactor from "../components/SecondFactor";
import { get, post } from "../api";

// Opened from an invite or password-reset email (/account/<code>). The person chooses their
// own password (the link works once), then goes through the second sign-in step: setting up
// 2FA for a new account, or entering their code after a reset.
export default function SetPassword({ code, onSignedIn, onDone }) {
  const [link, setLink] = useState(null);
  const [error, setError] = useState(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [secondStep, setSecondStep] = useState(null); // "setup" or "verify" once the password is saved

  useEffect(() => {
    get(`/account/link/${code}`)
      .then(setLink)
      .catch((err) => setError(err.message));
  }, [code]);

  function handleSubmit(event) {
    event.preventDefault();
    if (password !== confirm) {
      setError("The two passwords do not match.");
      return;
    }
    setSaving(true);
    setError(null);
    post(`/account/link/${code}`, { password })
      .then((result) => setSecondStep(result.requires_totp ? "verify" : "setup"))
      .catch((err) => setError(err.message))
      .finally(() => setSaving(false));
  }

  const isInvite = link?.purpose === "invite";

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
        {!link && error && (
          <div className="login-form panel">
            <h1>Link not valid</h1>
            <p className="subtitle">{error}</p>
            <button type="button" onClick={onDone}>
              Go to sign in
            </button>
          </div>
        )}

        {!link && !error && <p className="subtitle centered">Checking your link...</p>}

        {link && secondStep && <SecondFactor mode={secondStep} onDone={onSignedIn} />}

        {link && !secondStep && (
          <form className="login-form panel" onSubmit={handleSubmit}>
            <h1>{isInvite ? "Activate your account" : "Choose a new password"}</h1>
            <p className="subtitle">
              {isInvite ? "Welcome" : "Hello"}, {link.full_name || link.username}. Your username is{" "}
              <strong>{link.username}</strong>, and you can also sign in with {link.email}.
            </p>

            {/* Lets password managers save the new password against the right account */}
            <input type="text" name="username" autoComplete="username" value={link.username} readOnly hidden />

            <label>
              New password
              <input
                type="password"
                autoComplete="new-password"
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoFocus
                required
              />
            </label>
            <label>
              Confirm password
              <input
                type="password"
                autoComplete="new-password"
                minLength={8}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
              />
            </label>
            <p className="subtitle">At least 8 characters. This link works once.</p>

            {error && <p className="error">{error}</p>}

            <button type="submit" disabled={saving}>
              {saving ? "Saving..." : isInvite ? "Activate account" : "Save new password"}
            </button>
          </form>
        )}
      </main>
      <Footer />
    </div>
  );
}
