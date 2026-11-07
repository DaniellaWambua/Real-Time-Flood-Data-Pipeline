import { useEffect, useRef, useState } from "react";
import { post, verifyTotp } from "../api";
import "./SecondFactor.css";

// The second sign-in step every account goes through. "verify" asks for the code from the
// authenticator app; "setup" enrols an account that has no 2FA yet and then signs it in.
export default function SecondFactor({ mode, onDone }) {
  const [code, setCode] = useState("");
  const [setup, setSetup] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    if (mode !== "setup" || started.current) return;
    started.current = true; // one secret per visit, even when React runs effects twice in development
    post("/totp/setup", {})
      .then(setSetup)
      .catch((err) => setError(err.message));
  }, [mode]);

  function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const request = mode === "setup" ? post("/totp/enable", { code }) : verifyTotp(code);
    request
      .then((user) => onDone({ id: user.id, username: user.username, role: user.role }))
      .catch((err) => setError(err.message))
      .finally(() => setSubmitting(false));
  }

  const codeField = (
    <label>
      6-digit code
      <input
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
        inputMode="numeric"
        autoComplete="one-time-code"
        pattern="[0-9]{6}"
        autoFocus
        required
      />
    </label>
  );

  if (mode === "verify") {
    return (
      <form className="login-form panel" onSubmit={handleSubmit}>
        <h1>Enter your code</h1>
        <p className="subtitle">Open your authenticator app and enter the 6-digit code for this account.</p>
        {codeField}
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Verifying..." : "Verify"}
        </button>
      </form>
    );
  }

  return (
    <form className="login-form panel second-factor-setup" onSubmit={handleSubmit}>
      <h1>Set up two-factor sign-in</h1>
      <p className="subtitle">
        Every account signs in with a password and a code from an authenticator app. This takes about a minute
        and is only needed once.
      </p>
      <ol className="second-factor-steps">
        <li>Install an authenticator app on your phone, such as Google Authenticator or Microsoft Authenticator.</li>
        <li>In the app, add an account and scan this code.</li>
      </ol>
      {setup ? (
        <div className="second-factor-qr">
          <img src={`data:image/png;base64,${setup.qr_code_png_base64}`} alt="QR code to add this account to an authenticator app" />
          <p className="subtitle">
            Cannot scan it? Enter this key instead: <code className="second-factor-key">{setup.secret}</code>
          </p>
        </div>
      ) : (
        !error && <p className="subtitle">Preparing your code...</p>
      )}
      <ol className="second-factor-steps" start={3}>
        <li>Enter the 6-digit code the app now shows.</li>
      </ol>
      {codeField}
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={submitting || !setup}>
        {submitting ? "Checking..." : "Turn on and continue"}
      </button>
    </form>
  );
}
