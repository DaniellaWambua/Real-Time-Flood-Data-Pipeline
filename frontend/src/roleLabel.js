// The four roles from backend/config.py, with the names and one-line descriptions shown
// across the dashboard (sidebar, user management, invite dialog).
export const ROLE_OPTIONS = [
  {
    value: "disaster_management_agency",
    label: "Disaster Management Officer",
    description: "Views the overview, data stream, model results and alerts.",
  },
  {
    value: "emergency_responder",
    label: "Emergency Responder",
    description: "Views alerts and acknowledges and resolves them.",
  },
  {
    value: "government_official",
    label: "Government Official",
    description: "Views the overview and alerts.",
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
