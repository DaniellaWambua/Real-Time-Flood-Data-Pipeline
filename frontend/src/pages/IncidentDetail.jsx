import { useEffect, useState } from "react";
import StatusChip from "../components/StatusChip";
import IncidentResponses from "./IncidentResponses";
import { severityRole } from "../statusRoles";
import { confirmationTag } from "../provisional";
import { formatDay, OUTCOME_LABEL } from "../incidentFormat";
import { get, post } from "../api";

// One incident opened under its row (GET /api/incidents/<id>): each flagged day and its score, the
// verification decision, the field outcome, and the responses. Holds each role's actions on it:
// Disaster Management verifies or dismisses, Emergency Responders acknowledge and resolve.
export default function IncidentDetail({ id, role, onChanged }) {
  const [incident, setIncident] = useState(null);
  const [error, setError] = useState(null);
  const [reload, setReload] = useState(0);
  const [note, setNote] = useState("");
  const [outcome, setOutcome] = useState("");
  const [places, setPlaces] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get(`/api/incidents/${id}`)
      .then((row) => {
        setIncident(row);
        setError(null);
      })
      .catch((err) => setError(err.message));
  }, [id, reload]);

  async function run(path, body) {
    setBusy(true);
    try {
      await post(path, body);
      setNote("");
      setError(null);
      setReload((n) => n + 1);
      onChanged?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (error && !incident) return <p className="error">{error}</p>;
  if (!incident) return <p className="alert-responses-empty">Loading...</p>;

  const canVerify = role === "disaster_management_agency" && incident.verification === "pending";
  const canAct = role === "emergency_responder" && incident.verification === "verified" && incident.status !== "resolved";

  return (
    <div className="incident-detail">
      <div className="incident-detail-days">
        <h4 className="incident-detail-heading">Flagged days</h4>
        <ul className="detail-list">
          {incident.days_flagged.map((d) => (
            <li key={d.id}>
              <span className="figure">{formatDay(d.day)}</span>{" "}
              <StatusChip role={severityRole(d.severity)} label={d.severity} />{" "}
              <span className="figure">
                {d.anomaly_score.toFixed(3)} / {d.threshold_used.toFixed(3)}
              </span>{" "}
              <span className="alert-responses-by">{d.model_name}</span>
              {confirmationTag(d) && (
                <>
                  {" "}
                  <StatusChip {...confirmationTag(d)} />
                </>
              )}
            </li>
          ))}
        </ul>
      </div>

      <div className="incident-detail-state">
        <h4 className="incident-detail-heading">Verification</h4>
        {incident.verification === "pending" ? (
          <p className="alert-responses-empty">Waiting for a Disaster Management officer.</p>
        ) : (
          <p>
            {incident.verification === "verified" ? "Verified" : "Dismissed"} by {incident.verified_by},{" "}
            {new Date(incident.verified_at).toLocaleString()}
            {incident.verification_note && `: ${incident.verification_note}`}
          </p>
        )}
        {canVerify && (
          <div className="incident-detail-form">
            <input
              type="text"
              value={note}
              maxLength={1000}
              onChange={(e) => setNote(e.target.value)}
              placeholder="What the decision rests on (optional), e.g. Red Cross report from Mabatini"
              aria-label="Verification note"
            />
            <button type="button" disabled={busy} onClick={() => run(`/api/incidents/${id}/verification`, { decision: "verify", note })}>
              Verify
            </button>
            <button type="button" disabled={busy} onClick={() => run(`/api/incidents/${id}/verification`, { decision: "dismiss", note })}>
              Dismiss
            </button>
          </div>
        )}

        {incident.status === "resolved" && (
          <>
            <h4 className="incident-detail-heading">On the ground</h4>
            <p>
              {OUTCOME_LABEL[incident.outcome] ?? "Not recorded"}
              {incident.outcome_places && ` at ${incident.outcome_places}`}
              {incident.outcome_note && `: ${incident.outcome_note}`}. Resolved by {incident.resolved_by}.
            </p>
          </>
        )}

        {canAct && (
          <div className="incident-detail-actions">
            {incident.status === "active" && (
              <button type="button" disabled={busy} onClick={() => run(`/api/incidents/${id}/acknowledge`, {})}>
                Acknowledge
              </button>
            )}
            <fieldset className="incident-resolve">
              <legend>Resolve, and say what was found</legend>
              {Object.entries(OUTCOME_LABEL).map(([value, label]) => (
                <label key={value} className="incident-resolve-option">
                  <input type="radio" name={`outcome-${id}`} value={value} checked={outcome === value} onChange={() => setOutcome(value)} />
                  {label}
                </label>
              ))}
              <input
                type="text"
                value={places}
                maxLength={1000}
                onChange={(e) => setPlaces(e.target.value)}
                placeholder="Where flooding was found, e.g. Mabatini, Kosovo bridge"
                aria-label="Places"
              />
              <input
                type="text"
                value={note}
                maxLength={1000}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Anything else (optional)"
                aria-label="Outcome note"
              />
              <button
                type="button"
                disabled={busy || !outcome}
                onClick={() => run(`/api/incidents/${id}/resolve`, { outcome, places, note })}
              >
                Resolve
              </button>
            </fieldset>
          </div>
        )}
        {error && <p className="error">{error}</p>}
      </div>

      <IncidentResponses incident={incident} role={role} onAdded={() => { setReload((n) => n + 1); onChanged?.(); }} />
    </div>
  );
}
