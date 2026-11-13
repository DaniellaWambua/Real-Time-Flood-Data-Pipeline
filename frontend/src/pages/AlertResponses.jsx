import { useEffect, useState } from "react";
import { get, post } from "../api";

// What has been done about one alert (GET/POST /api/alerts/<id>/responses). Emergency
// Responders record field updates, Government Officials record the resources they
// allocated, and either records recovery work once the alert is resolved. Every role
// that can open Alerts reads the same history.
const KIND_LABEL = { field: "Field update", resources: "Resources allocated", recovery: "Recovery work" };
const KINDS_BY_ROLE = {
  emergency_responder: ["field", "recovery"],
  government_official: ["resources", "recovery"],
};

function kindsFor(role, status) {
  const kinds = KINDS_BY_ROLE[role] ?? [];
  return kinds.filter((k) => (status === "resolved" ? k === "recovery" : k !== "recovery"));
}

export default function AlertResponses({ alert, role, onAdded }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const kinds = kindsFor(role, alert.status);
  const [kind, setKind] = useState(kinds[0] ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get(`/api/alerts/${alert.id}/responses`)
      .then(setRows)
      .catch((err) => setError(err.message));
  }, [alert.id]);

  async function submit(event) {
    event.preventDefault();
    if (!note.trim()) return;
    setBusy(true);
    try {
      const row = await post(`/api/alerts/${alert.id}/responses`, { kind, note });
      setRows((current) => [...(current ?? []), row]);
      setNote("");
      setError(null);
      onAdded?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="alert-responses">
      {rows && rows.length === 0 && <p className="alert-responses-empty">Nothing has been recorded for this alert yet.</p>}
      {rows && rows.length > 0 && (
        <ol className="alert-responses-list">
          {rows.map((r) => (
            <li key={r.id}>
              <span className="alert-responses-kind">{KIND_LABEL[r.kind] ?? r.kind}</span>
              <span className="alert-responses-note">{r.note}</span>
              <span className="alert-responses-by">
                {r.author}, {new Date(r.created_at).toLocaleString()}
              </span>
            </li>
          ))}
        </ol>
      )}
      {kinds.length > 0 && (
        <form className="alert-responses-form" onSubmit={submit}>
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Type of response">
            {kinds.map((k) => (
              <option key={k} value={k}>
                {KIND_LABEL[k]}
              </option>
            ))}
          </select>
          <input
            type="text"
            value={note}
            maxLength={1000}
            onChange={(e) => setNote(e.target.value)}
            placeholder={kind === "resources" ? "e.g. two rescue boats and 50 tents sent to Mabatini" : "What was done"}
            aria-label="Response note"
          />
          <button type="submit" disabled={busy || !note.trim()}>
            Record
          </button>
        </form>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
