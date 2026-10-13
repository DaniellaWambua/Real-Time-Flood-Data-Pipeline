// Domain severities/statuses mapped onto StatusChip's roles
// (good/warning/serious/critical, plus the neutral "muted" for an
// honest off state rather than a severity). Split out from
// StatusChip.jsx itself so that file stays component-only (oxlint's
// react/only-export-components: fast refresh only works when a file
// exports just components).
const SEVERITY_ROLE = { low: "good", medium: "warning", high: "critical" };
// Per Daniella's explicit request, a disconnected source is now red
// (critical) rather than the neutral "muted" gray used before - the
// one place this project colors a connection state the same as a
// severity, overriding the earlier reasoning that kept the two
// separate. "muted" is still used for a deactivated user account,
// which is left unchanged.
const CONNECTION_ROLE = { connected: "good", disconnected: "critical" };

export function severityRole(severity) {
  return SEVERITY_ROLE[severity] ?? "serious";
}

export function connectionRole(status) {
  return CONNECTION_ROLE[status] ?? "serious";
}

// The status column (active/resolved) is deliberately independent of
// the severity column: severity never changes once raised, and the
// severity column already shows it, so status reads as a plain
// workflow state - active (blue) or resolved (good) - rather than
// re-coloring by severity too.
export function alertStatusRole(alert) {
  return alert.status === "resolved" ? "good" : "active";
}
