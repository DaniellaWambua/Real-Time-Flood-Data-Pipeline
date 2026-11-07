import { useEffect, useState } from "react";
import Dialog from "../../components/Dialog";
import { ROLE_OPTIONS } from "../../roleLabel";
import { get, post } from "../../api";

// Invite by email: the person receives a single-use link and chooses their own password,
// so the administrator never sets or sees it.
export default function InviteUserDialog({ onClose, onInvited }) {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [organisation, setOrganisation] = useState("");
  const [role, setRole] = useState("");
  const [organisations, setOrganisations] = useState([]);
  const [error, setError] = useState(null);
  const [sending, setSending] = useState(false);
  const [sentTo, setSentTo] = useState(null);

  useEffect(() => {
    get("/api/users/organisations")
      .then(setOrganisations)
      .catch(() => setOrganisations([]));
  }, []);

  function reset() {
    setEmail("");
    setFullName("");
    setOrganisation("");
    setRole("");
    setError(null);
    setSentTo(null);
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (!role) {
      setError("Choose a role for this person.");
      return;
    }
    setSending(true);
    setError(null);
    post("/api/users/invite", { email, full_name: fullName, organisation, role })
      .then((user) => {
        onInvited(user);
        setSentTo(user.email);
      })
      .catch((err) => setError(err.message))
      .finally(() => setSending(false));
  }

  if (sentTo) {
    return (
      <Dialog title="Invite sent" onClose={onClose} width={460}>
        <p className="invite-sent-text">
          An invite has been emailed to <strong>{sentTo}</strong>. The link works once and expires in 72
          hours. Until it is used, the person shows as Invited in the users list.
        </p>
        <div className="app-dialog-actions">
          <button type="button" onClick={reset}>
            Invite another
          </button>
          <button type="button" className="btn-primary" onClick={onClose}>
            Done
          </button>
        </div>
      </Dialog>
    );
  }

  return (
    <Dialog
      title="Invite a user"
      description="They will receive an email with a link to activate their account and choose a password."
      onClose={onClose}
    >
      <form onSubmit={handleSubmit} autoComplete="off" className="invite-form">
        <label className="invite-field">
          Email address
          <input
            type="email"
            name="invite-email"
            autoComplete="off"
            placeholder="name@organisation.org"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoFocus
            required
          />
        </label>

        <div className="invite-field-row">
          <label className="invite-field">
            Full name
            <input
              type="text"
              name="invite-full-name"
              autoComplete="off"
              placeholder="Jane Wanjiru"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
          </label>
          <label className="invite-field">
            Organisation
            <input
              type="text"
              name="invite-organisation"
              autoComplete="off"
              list="invite-organisations"
              placeholder="Nairobi County"
              value={organisation}
              onChange={(e) => setOrganisation(e.target.value)}
            />
            <datalist id="invite-organisations">
              {organisations.map((o) => (
                <option key={o} value={o} />
              ))}
            </datalist>
          </label>
        </div>

        <fieldset className="invite-roles">
          <legend>Role</legend>
          {ROLE_OPTIONS.map((r) => (
            <label key={r.value} className={`invite-role-card${role === r.value ? " selected" : ""}`}>
              <input
                type="radio"
                name="invite-role"
                value={r.value}
                checked={role === r.value}
                onChange={() => setRole(r.value)}
              />
              <span className="invite-role-name">{r.label}</span>
              <span className="invite-role-description">{r.description}</span>
            </label>
          ))}
        </fieldset>

        {error && <p className="error">{error}</p>}

        <div className="app-dialog-actions">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" disabled={sending}>
            {sending ? "Sending invite..." : "Send invite"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
