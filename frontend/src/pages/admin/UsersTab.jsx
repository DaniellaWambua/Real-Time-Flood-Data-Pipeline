import { useEffect, useMemo, useState } from "react";
import Avatar from "../../components/Avatar";
import StatusChip from "../../components/StatusChip";
import Dialog from "../../components/Dialog";
import EmptyState from "../../components/EmptyState";
import { ROLE_OPTIONS, roleLabel } from "../../roleLabel";
import { get, patch, post } from "../../api";
import { downloadCsv } from "../../csv";
import InviteUserDialog from "./InviteUserDialog";
import EditUserDialog from "./EditUserDialog";
import "./UsersTab.css";

const STATUS = {
  active: { label: "Active", role: "good" },
  invited: { label: "Invited", role: "active" },
  invite_expired: { label: "Invite expired", role: "warning" },
  deactivated: { label: "Deactivated", role: "muted" },
};

function displayName(user) {
  return user.full_name || user.username;
}

function formatDate(iso) {
  return iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "Never";
}

function exportCsv(rows) {
  downloadCsv(
    "users",
    ["Name", "Username", "Email", "Organisation", "Role", "Status", "Last sign-in", "Created"],
    rows.map((u) => [displayName(u), u.username, u.email, u.organisation, roleLabel(u.role), STATUS[u.status]?.label,
      u.last_sign_in ?? "", u.created_at]),
  );
}

function RowMenu({ user, isSelf, onAction }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    const close = () => setOpen(false);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [open]);

  const items = [{ id: "edit", label: "Edit details" }];
  if (user.status === "invited" || user.status === "invite_expired") items.push({ id: "resend", label: "Resend invite" });
  if (user.status === "active") items.push({ id: "reset", label: "Send password reset link" });
  if (user.totp_enabled && !isSelf) items.push({ id: "reset2fa", label: "Reset two-factor sign-in" });
  if (user.status === "deactivated") items.push({ id: "reactivate", label: "Reactivate" });
  else if (!isSelf) items.push({ id: "deactivate", label: "Deactivate", danger: true });

  return (
    <div className="row-menu">
      <button
        type="button"
        className="row-menu-trigger"
        aria-label={`Actions for ${displayName(user)}`}
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        ⋯
      </button>
      {open && (
        <ul className="row-menu-list" role="menu">
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                role="menuitem"
                className={item.danger ? "row-menu-danger" : ""}
                onClick={() => onAction(item.id, user)}
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// Administration's Users tab: everyone with access, searchable and exportable, with invites
// by email and per-person actions.
export default function UsersTab({ currentUserId }) {
  const [users, setUsers] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [inviting, setInviting] = useState(false);
  const [editing, setEditing] = useState(null);
  const [confirming, setConfirming] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get("/api/users")
      .then(setUsers)
      .catch((err) => setError(err.message));
  }, []);

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (users ?? []).filter(
      (u) =>
        (!roleFilter || u.role === roleFilter) &&
        (!statusFilter || u.status === statusFilter) &&
        (!q || [u.full_name, u.username, u.email, u.organisation].some((v) => v?.toLowerCase().includes(q))),
    );
  }, [users, search, roleFilter, statusFilter]);

  function replaceUser(updated) {
    setUsers((current) => {
      const exists = (current ?? []).some((u) => u.id === updated.id);
      const next = exists ? current.map((u) => (u.id === updated.id ? updated : u)) : [...(current ?? []), updated];
      return next.sort((a, b) => displayName(a).localeCompare(displayName(b)));
    });
  }

  function run(request, success) {
    setBusy(true);
    setNotice(null);
    request
      .then((result) => {
        if (result && result.id) replaceUser(result);
        setNotice({ type: "success", text: success });
      })
      .catch((err) => setNotice({ type: "error", text: err.message }))
      .finally(() => {
        setBusy(false);
        setConfirming(null);
      });
  }

  function handleAction(action, user) {
    if (action === "edit") setEditing(user);
    if (action === "resend") run(post(`/api/users/${user.id}/resend-invite`, {}), `A new invite was sent to ${user.email}.`);
    if (action === "reset") run(post(`/api/users/${user.id}/send-reset`, {}), `A password reset link was sent to ${user.email}.`);
    if (action === "reactivate") run(patch(`/api/users/${user.id}`, { is_active: true }), `${displayName(user)} can sign in again.`);
    if (action === "deactivate") setConfirming(user);
    if (action === "reset2fa")
      run(post(`/api/users/${user.id}/reset-2fa`, {}), `${displayName(user)} will set up two-factor sign-in again at their next sign-in.`);
  }

  if (error) return <p className="error">{error}</p>;

  return (
    <div className="panel users-panel">
      <div className="users-header">
        <div>
          <h2 className="panel-title">Users</h2>
          <p className="users-subtitle">
            {users ? `${users.length} people have access to the system.` : "Loading users..."}
          </p>
        </div>
        <div className="users-header-actions">
          <button type="button" onClick={() => exportCsv(shown)} disabled={!shown.length}>
            Export CSV
          </button>
          <button type="button" className="btn-primary" onClick={() => setInviting(true)}>
            Invite user
          </button>
        </div>
      </div>

      <div className="users-toolbar">
        <input
          type="search"
          className="users-search"
          placeholder="Search name, username, email or organisation"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search users"
        />
        <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} aria-label="Filter by role">
          <option value="">All roles</option>
          {ROLE_OPTIONS.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option>
          {Object.entries(STATUS).map(([value, s]) => (
            <option key={value} value={value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>

      {notice && <p className={`users-notice users-notice--${notice.type}`}>{notice.text}</p>}

      {users && shown.length === 0 && <EmptyState>No users match these filters.</EmptyState>}

      {shown.length > 0 && (
        <div className="users-table-scroll">
          <table className="admin-table users-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Organisation</th>
                <th>Role</th>
                <th>Status</th>
                <th>Last sign-in</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {shown.map((u) => {
                const isSelf = u.id === currentUserId;
                return (
                  <tr key={u.id}>
                    <td>
                      <div className="users-person">
                        <Avatar name={displayName(u)} />
                        <div>
                          <div className="admin-table-strong">
                            {displayName(u)}
                            {isSelf && <span className="admin-you-badge">You</span>}
                          </div>
                          <div className="admin-table-subtext">@{u.username}</div>
                        </div>
                      </div>
                    </td>
                    <td>{u.email ?? "—"}</td>
                    <td>{u.organisation ?? "—"}</td>
                    <td>{roleLabel(u.role)}</td>
                    <td>
                      <StatusChip role={STATUS[u.status]?.role} label={STATUS[u.status]?.label ?? u.status} />
                      {u.status === "active" && (
                        <div className="admin-table-subtext">{u.totp_enabled ? "2FA on" : "2FA set up at next sign-in"}</div>
                      )}
                      {u.status === "invited" && (
                        <div className="admin-table-subtext">Link expires {formatDate(u.invite_expires_at)}</div>
                      )}
                    </td>
                    <td className="figure">{formatDate(u.last_sign_in)}</td>
                    <td className="users-actions-cell">
                      <RowMenu user={u} isSelf={isSelf} onAction={handleAction} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {users && (
        <p className="users-count">
          Showing {shown.length} of {users.length}
        </p>
      )}

      {inviting && (
        <InviteUserDialog
          onClose={() => setInviting(false)}
          onInvited={(user) => {
            replaceUser(user);
            setNotice({ type: "success", text: `Invite sent to ${user.email}.` });
          }}
        />
      )}

      {editing && (
        <EditUserDialog
          user={editing}
          isSelf={editing.id === currentUserId}
          onClose={() => setEditing(null)}
          onSaved={(user) => {
            replaceUser(user);
            setNotice({ type: "success", text: `Saved changes to ${displayName(user)}.` });
          }}
        />
      )}

      {confirming && (
        <Dialog title={`Deactivate ${displayName(confirming)}?`} onClose={() => setConfirming(null)} width={440}>
          <p className="invite-sent-text">
            They will no longer be able to sign in. Their history, such as alerts they acknowledged, stays in the
            system, and you can reactivate them at any time.
          </p>
          <div className="app-dialog-actions">
            <button type="button" onClick={() => setConfirming(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-danger"
              disabled={busy}
              onClick={() =>
                run(patch(`/api/users/${confirming.id}`, { is_active: false }), `${displayName(confirming)} has been deactivated.`)
              }
            >
              Deactivate
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
