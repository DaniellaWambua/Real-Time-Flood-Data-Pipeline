// The four roles from backend/config.py, with the names and one-line descriptions shown
// across the dashboard (sidebar, user management, invite dialog).
export const ROLE_OPTIONS = [
  {
    value: "disaster_management_agency",
    label: "Disaster Management Officer",
    description: "Monitors the readings and the model, and verifies or dismisses each new incident before the field is told.",
  },
  {
    value: "emergency_responder",
    label: "Emergency Responder",
    description: "Acknowledges and resolves verified incidents, recording whether flooding was found.",
  },
  {
    value: "government_official",
    label: "Government Official",
    description: "Follows verified incidents and records the resources allocated to them.",
  },
  {
    value: "system_administrator",
    label: "System Administrator",
    description: "Manages users, data sources and system activity.",
  },
];

export function roleLabel(role) {
  return ROLE_OPTIONS.find((r) => r.value === role)?.label ?? role.replace(/_/g, " ");
}
