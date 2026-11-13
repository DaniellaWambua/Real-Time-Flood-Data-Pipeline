// Provisional alerts come from the fast model, which scores a day before CHIRPS rainfall is published
// (about six weeks late). The full model later confirms the alert or marks it not confirmed
// (backend/flood_detection.py). These helpers give every screen the same wording.

// { role, label } for StatusChip, or null for an ordinary full-model alert or incident. An incident
// carries the same fields, rolled up from its days: provisional while every day is.
export function confirmationTag(item) {
  if (item.provisional || item.confirmation === "provisional") return { role: "warning", label: "provisional" };
  if (item.confirmation === "confirmed") return { role: "good", label: "confirmed" };
  if (item.confirmation === "not_confirmed") return { role: "muted", label: "not confirmed" };
  return null;
}

// How long after the flood day the alert was raised, e.g. "raised 8 days later"
export function raisedAfter(floodDay, createdAt) {
  const days = Math.round((new Date(createdAt) - new Date(floodDay)) / 86400000);
  if (days <= 0) return "raised the same day";
  return `raised ${days} day${days === 1 ? "" : "s"} later`;
}
