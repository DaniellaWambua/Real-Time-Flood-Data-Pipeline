// Maps severities and statuses onto StatusChip roles (kept out of StatusChip.jsx for fast refresh).
const SEVERITY_ROLE = { low: "good", medium: "warning", high: "critical" };
// A disconnected source shows red.
const CONNECTION_ROLE = { connected: "good", disconnected: "critical" };

export function severityRole(severity) {
  return SEVERITY_ROLE[severity] ?? "serious";
}

export function connectionRole(status) {
  return CONNECTION_ROLE[status] ?? "serious";
}

// Status is a workflow state independent of severity.
export function alertStatusRole(alert) {
  if (alert.status === "resolved") return "good";
  return alert.status === "acknowledged" ? "muted" : "active";
}

// Verification of an incident by a Disaster Management officer: still waiting (warning), verified
// (active, it is now the field's to work), or dismissed as a false alarm (muted).
const VERIFICATION_ROLE = { pending: "warning", verified: "active", dismissed: "muted" };

export function verificationRole(verification) {
  return VERIFICATION_ROLE[verification] ?? "serious";
}
