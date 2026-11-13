// Per-role screen access, matching the proposal's wireframes (3.4.6):
// Main Dashboard is the landing screen for every authenticated role;
// Data Stream Monitor is for Disaster Management Agency; Incidents (the
// proposal's Alert Management) is verified by Disaster Management Officers,
// then worked by Emergency Responders and Government Officials, who see only
// verified incidents; Notifications is for the three roles that are told about
// incidents and rain forecasts;
// System Administration is for the admin. LSTM Anomaly is not one of
// the proposal's four screens (added later), kept alongside Disaster
// Management Agency's other analytical screen.
//
// Shared by Layout.jsx (which links are shown in the sidebar) and
// App.jsx (which routes actually render, so typing a hidden URL in
// directly does not work either), so the two can never drift apart.
// A path missing from ROUTE_ROLES, or mapped to undefined, is open to
// every authenticated role.
export const ROUTE_ROLES = {
  "/": undefined,
  "/data-stream": ["disaster_management_agency", "system_administrator"],
  "/lstm-anomaly": ["disaster_management_agency", "system_administrator"],
  "/incidents": ["disaster_management_agency", "emergency_responder", "government_official", "system_administrator"],
  "/notifications": ["disaster_management_agency", "emergency_responder", "government_official"],
  "/admin": ["system_administrator"],
  "/role-switcher": undefined,
};

export function canAccess(role, path) {
  const roles = ROUTE_ROLES[path];
  return !roles || roles.includes(role);
}
