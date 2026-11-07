import "./Avatar.css";

// Soft background tones with dark text, chosen per person from their name so the same
// person always gets the same colour.
const TONES = ["#dbeafe", "#dcfce7", "#fef3c7", "#fce7f3", "#e0e7ff", "#ccfbf1", "#ffedd5", "#ede9fe"];

function initials(name) {
  const parts = name.trim().split(/[\s._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "?") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

export default function Avatar({ name, size = 36 }) {
  const tone = TONES[[...name].reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % TONES.length];
  return (
    <span
      className="avatar"
      style={{ width: size, height: size, fontSize: size * 0.38, background: tone }}
      aria-hidden="true"
    >
      {initials(name)}
    </span>
  );
}
