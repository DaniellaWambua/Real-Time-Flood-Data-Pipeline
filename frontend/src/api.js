// Thin fetch wrapper for the Flask backend (backend/app.py). Every call
// sends credentials so the session cookie set by /login travels with it,
// which is why CORS on the backend (config.FRONTEND_ORIGINS) has to name
// this dev server's exact origin rather than using a wildcard.
//
// Host here has to match the host the frontend itself is served from
// (localhost, not 127.0.0.1, see vite.config.js), not just the port.
// They are the same machine either way, but browsers treat "localhost"
// and "127.0.0.1" as different sites, so a mismatch here means the
// session cookie /login sets never gets attached to later requests,
// every dashboard endpoint then fails with "authentication required"
// even though login itself appeared to work.
//
// Defaults to the backend's documented dev port (backend/config.py's
// API_PORT, 5001 by default because macOS's AirPlay Receiver sits on
// 5000). Override with a .env.local file (VITE_API_BASE=...) if you run
// the backend somewhere else.
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:5001";

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

// Second step of login for an account with 2FA enabled (backend/
// routes_auth.py). Only called once login() has already returned
// { requires_totp: true }.
export function verifyTotp(code) {
  return request("/login/verify-totp", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

// Google Sign-In's alternative to login(): credential is the ID token
// Google Identity Services hands back after the user picks an account.
// Returns the same shape login() does, including { requires_totp: true }
// when the matched account also has 2FA on.
export function loginWithGoogle(credential) {
  return request("/login/google", {
    method: "POST",
    body: JSON.stringify({ credential }),
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

export function post(path, body) {
  return request(path, { method: "POST", body: JSON.stringify(body) });
}

export function patch(path, body) {
  return request(path, { method: "PATCH", body: JSON.stringify(body) });
}
