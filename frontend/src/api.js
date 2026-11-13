// Fetch wrapper for the Flask backend. Every call sends the session cookie.
// The host must match the one the frontend is served from (localhost, not 127.0.0.1),
// or the browser will not send the cookie. Override with VITE_API_BASE.
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

// Second sign-in step for accounts with two-factor authentication.
export function verifyTotp(code) {
  return request("/login/verify-totp", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

// Google sign-in: credential is the ID token from Google Identity Services.
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
