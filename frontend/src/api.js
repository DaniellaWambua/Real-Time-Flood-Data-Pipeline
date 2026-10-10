// Thin fetch wrapper for the Flask backend (backend/app.py). Every call
// sends credentials so the session cookie set by /login travels with it,
// which is why CORS on the backend (config.FRONTEND_ORIGINS) has to name
// this dev server's exact origin rather than using a wildcard.
//
// Defaults to the backend's documented dev port (backend/config.py's
// API_PORT, 5001 by default because macOS's AirPlay Receiver sits on
// 5000). Override with a .env.local file (VITE_API_BASE=...) if you run
// the backend somewhere else.
const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:5001";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  const body = await res.json().catch(() => null);

  if (!res.ok) {
    const message = body && body.error ? body.error : `request failed (HTTP ${res.status})`;
    throw new Error(message);
  }

  return body;
}

export function login(username, password) {
  return request("/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function logout() {
  return request("/logout", { method: "POST" });
}

export function me() {
  return request("/me");
}

export function get(path, params = {}) {
  const cleaned = Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== ""),
  );
  const query = new URLSearchParams(cleaned).toString();
  return request(`${path}${query ? `?${query}` : ""}`);
}
