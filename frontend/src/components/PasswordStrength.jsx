import { useEffect, useState } from "react";
import { assess } from "../passwordStrength";
import "./PasswordStrength.css";

const LABELS = ["Too weak", "Too weak", "Weak", "Strong", "Very strong"];

// A four-segment meter under a new-password field, with one line saying what to change.
// onChange receives true once the password meets the rules.
export default function PasswordStrength({ password, person, onChange }) {
  const [state, setState] = useState({ score: 0, ok: false, message: "" });

  useEffect(() => {
    let current = true;
    assess(password, person).then((result) => {
      if (!current) return;
      setState(result);
      onChange?.(result.ok);
    });
    return () => {
      current = false;
    };
    // person is rebuilt on every render by callers; its fields are what matter
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [password, person?.username, person?.email]);

  if (!password) {
    return <p className="password-strength-hint">At least 12 characters. A few unrelated words work well.</p>;
  }

  const level = state.ok ? state.score : Math.min(state.score, 2);
  return (
    <div className="password-strength" aria-live="polite">
      <div className="password-strength-bar" aria-hidden="true">
        {[1, 2, 3, 4].map((n) => (
          <span
            key={n}
            className={`password-strength-segment${n <= Math.max(level, 1) ? ` password-strength-segment--${state.ok ? "good" : level >= 2 ? "fair" : "weak"}` : ""}`}
          />
        ))}
      </div>
      <p className={`password-strength-hint${state.ok ? " password-strength-hint--good" : ""}`}>
        <strong>{state.ok ? LABELS[state.score] : LABELS[level]}.</strong> {state.ok ? "" : state.message}
      </p>
    </div>
  );
}
