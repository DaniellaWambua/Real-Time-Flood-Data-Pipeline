import { useState } from "react";
import Dialog from "../../components/Dialog";
import { ROLE_OPTIONS } from "../../roleLabel";
import { patch } from "../../api";

// Edit a user's name, organisation, email and role. Passwords are never set here: the person
// is sent a reset link instead. The email is where links are sent and the Google account
// they can sign in with.
export default function EditUserDialog({ user, isSelf, onClose, onSaved }) {
  const [fullName, setFullName] = useState(user.full_name ?? "");
  const [organisation, setOrganisation] = useState(user.organisation ?? "");
  const [email, setEmail] = useState(user.email ?? "");
  const [role, setRole] = useState(user.role);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    patch(`/api/users/${user.id}`, { full_name: fullName, organisation, role, ...(email ? { email } : {}) })
      .then((updated) => {
        onSaved(updated);
        onClose();
      })
      .catch((err) => setError(err.message))
      .finally(() => setSaving(false));
  }

  return (
    <Dialog title="Edit user" description={`@${user.username}`} onClose={onClose} width={480}>
      <form onSubmit={handleSubmit} autoComplete="off" className="invite-form">
        <label className="invite-field">
          Full name
          <input value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="off" required />
        </label>
        <label className="invite-field">
          Organisation
          <input value={organisation} onChange={(e) => setOrganisation(e.target.value)} autoComplete="off" />
        </label>
        <label className="invite-field">
          Email address
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="off"
            required={Boolean(user.email)}
          />
          <span className="invite-hint">Used for invite and reset links, and for signing in with Google.</span>
        </label>
        <label className="invite-field">
          Role
          <select value={role} onChange={(e) => setRole(e.target.value)} disabled={isSelf}>
            {ROLE_OPTIONS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
          {isSelf && <span className="invite-hint">You cannot change your own role.</span>}
        </label>

        {error && <p className="error">{error}</p>}

        <div className="app-dialog-actions">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" disabled={saving}>
            {saving ? "Saving..." : "Save changes"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
