// Used by DataStream's selected-river "Last reading" detail, so a
// compact shape ("31 Dec 2025, 03:00") is available in one place
// rather than hand-rolled inline.
export function formatCompactTimestamp(value) {
  const date = value instanceof Date ? value : new Date(value);
  const datePart = date.toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
  const timePart = date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return `${datePart}, ${timePart}`;
}
