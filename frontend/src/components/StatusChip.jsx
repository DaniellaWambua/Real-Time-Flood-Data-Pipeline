import "./StatusChip.css";

// Shared severity/status vocabulary across the dashboard. Each role maps
// to one of the dataviz skill's four reserved status colors, which are
// never used for anything else (no series, no accent). A shape rides
// alongside the color (never color alone, per that skill's rule, since
// two of these four fall under 3:1 contrast on the light surface by
// design, and color blindness is a second, separate reason not to rely
// on hue), and the label is always visible text, not a tooltip-only hint.
// The domain -> role mappings themselves live in ../statusRoles.js, kept
// out of this file so it stays component-only.
const ROLES = {
  good: { glyph: "●", className: "status-good" },
  warning: { glyph: "▲", className: "status-warning" },
  serious: { glyph: "◆", className: "status-serious" },
  critical: { glyph: "✕", className: "status-critical" },
};

export default function StatusChip({ role, label }) {
  const { glyph, className } = ROLES[role] ?? ROLES.serious;
  return (
    <span className={`status-chip ${className}`}>
      <span className="status-chip-glyph" aria-hidden="true">
        {glyph}
      </span>
      {label}
    </span>
  );
}
