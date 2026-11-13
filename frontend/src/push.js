// Web Push for the installed app: the service worker (public/sw.js) shows notifications the backend
// sends (backend/notify.py) even when the dashboard is closed. Needs the server's VAPID public key
// (GET /api/push/key) and the user's permission; without either, notifications stay in the app only.
import { get, post } from "./api";

export function pushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

export function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

function toKey(base64) {
  const padded = (base64 + "=".repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

// "on", "off", "blocked" or "unavailable" (no browser support, or push not set up on the server)
export async function pushState() {
  if (!pushSupported()) return "unavailable";
  const { key } = await get("/api/push/key");
  if (!key) return "unavailable";
  if (Notification.permission === "denied") return "blocked";
  const registration = await navigator.serviceWorker.ready;
  return (await registration.pushManager.getSubscription()) ? "on" : "off";
}

export async function turnPushOn() {
  const { key } = await get("/api/push/key");
  if (!key) throw new Error("Push notifications are not set up on this server yet.");
  if ((await Notification.requestPermission()) !== "granted") throw new Error("Notifications were not allowed.");
  const registration = await navigator.serviceWorker.ready;
  const subscription =
    (await registration.pushManager.getSubscription()) ??
    (await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: toKey(key) }));
  await post("/api/push/subscribe", subscription.toJSON());
}

export async function turnPushOff() {
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (!subscription) return;
  await post("/api/push/unsubscribe", { endpoint: subscription.endpoint });
  await subscription.unsubscribe();
}
