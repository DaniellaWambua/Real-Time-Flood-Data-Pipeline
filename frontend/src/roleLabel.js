// Shared between the sidebar (Layout.jsx) and the user-management table
// (Admin.jsx), so "system_administrator" reads as "system
// administrator" the same way in both places rather than drifting.
export function roleLabel(role) {
  return role.replace(/_/g, " ");
}
