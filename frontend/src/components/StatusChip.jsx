import "./StatusChip.css";

// Status shown as coloured text. The domain-to-role mappings live in ../statusRoles.js.
const ROLES = {
  good: "status-good",
  warning: "status-warning",
  serious: "status-serious",
  critical: "status-critical",
  muted: "status-muted",
  active: "status-active",
};

export default function StatusChip({ role, label }) {
  const className = ROLES[role] ?? ROLES.serious;
  return <span className={`status-chip ${className}`}>{label}</span>;
}
