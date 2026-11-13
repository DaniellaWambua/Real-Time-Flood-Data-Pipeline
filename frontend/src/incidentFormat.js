// Shared wording for incident dates (Incidents, Overview and Notifications screens).
// A flood day is stored as midnight UTC, so dates are read in UTC.
export function formatDay(iso) {
  return new Date(iso).toLocaleDateString("en-GB", { timeZone: "UTC" });
}

export function formatSpan(incident) {
  if (incident.start_day === incident.end_day) return formatDay(incident.start_day);
  return `${formatDay(incident.start_day)} to ${formatDay(incident.end_day)}`;
}

export const OUTCOME_LABEL = {
  flooding_observed: "Flooding found",
  no_flooding: "No flooding found",
  not_checked: "Not checked on the ground",
};
