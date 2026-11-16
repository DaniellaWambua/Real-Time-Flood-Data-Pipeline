// Which roles can open each screen. Used by Layout.jsx for the sidebar and App.jsx for the routes,
// so both stay in step. A path not listed is open to every signed-in role.
export const ROUTE_ROLES = {
  "/": undefined,
  "/data-stream": ["disaster_management_agency", "system_administrator"],
  "/lstm-anomaly": ["disaster_management_agency", "system_administrator"],
  "/incidents": ["disaster_management_agency", "emergency_responder", "government_official", "system_administrator"],
  "/notifications": ["disaster_management_agency", "emergency_responder", "government_official"],
  "/admin": ["system_administrator"],
  "/settings": undefined,
};

// The screens shown in the sidebar, used by Settings to list what the signed-in role can open.
export const SCREENS = [
  { path: "/", label: "Overview" },
  { path: "/data-stream", label: "Data stream" },
  { path: "/lstm-anomaly", label: "LSTM anomaly" },
  { path: "/incidents", label: "Incidents" },
  { path: "/notifications", label: "Notifications" },
  { path: "/admin", label: "Administration" },
];

export function canAccess(role, path) {
  const roles = ROUTE_ROLES[path];
  return !roles || roles.includes(role);
}
