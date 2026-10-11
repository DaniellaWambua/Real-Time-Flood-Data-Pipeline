// Domain severities/statuses mapped onto StatusChip's four roles
// (good/warning/serious/critical). Split out from StatusChip.jsx itself
// so that file stays component-only (oxlint's react/only-export-components:
// fast refresh only works when a file exports just components).
const SEVERITY_ROLE = { low: "good", medium: "warning", high: "critical" };
const CONNECTION_ROLE = { connected: "good", disconnected: "serious" };

export function severityRole(severity) {
  return SEVERITY_ROLE[severity] ?? "serious";
}

export function connectionRole(status) {
  return CONNECTION_ROLE[status] ?? "serious";
}

// The status column (active/resolved) is deliberately a separate chip
// from the severity column: severity never changes once raised, but
// status should read as calm once resolved, not still carry the
// original severity's color.
export function alertStatusRole(alert) {
  if (alert.status === "resolved") return "good";
  return severityRole(alert.severity);
}
