import "./StatusChip.css";

// Shared severity/status vocabulary across the dashboard. Each role
// maps to a text color only now (no pill background, no glyph) per
// Daniella's request to drop the rounded chip/circle entirely: good
// (green), warning (orange), critical (red), muted (neutral gray,
// for an honest off state), and active (blue, an alert's workflow
// state independent of severity). The domain -> role mappings
// themselves live in ../statusRoles.js, kept out of this file so it
// stays component-only.
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
