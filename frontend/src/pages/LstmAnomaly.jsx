import { useEffect, useState } from "react";
import PageHeader from "../components/PageHeader";
import MetricCard from "../components/MetricCard";
import EmptyState from "../components/EmptyState";
import { get } from "../api";
import "./LstmAnomaly.css";

// Real numbers from claude/training-results.md (Phase 9: all three
// ERA5-Land features together, the feature set Phase 10 kept as
// final, narrowed train/validation split, drift-conditional pooled
// threshold - the method actually in use, not train.py's own simpler
// per-catchment threshold). This is the closest existing run to the
// project's final configuration, but it still includes Nzoia River,
// since removed from the system (see project-checklist.md, Phase 10);
// the final six-catchment confirmation run has not been done yet.
// These are static content, not fetched from the backend - there is
// no live model-metrics endpoint, and these numbers only change when
// a new training run is logged, not on every page load. Update this
// block (and the proposal-target comparison below) once that final
// run lands.
const COMBINED = { precision: 0.113, recall: 0.541, f1: 0.187 };

const PROPOSAL_TARGET = { f1: 0.7, recall: 0.75 };

const PER_CATCHMENT = [
  { catchment: "Nairobi River", precision: 0.085, recall: 1.0, f1: 0.157 },
  { catchment: "Mathare", precision: 0.636, recall: 0.7, f1: 0.667 },
  { catchment: "Ngong", precision: 0.182, recall: 1.0, f1: 0.308 },
  { catchment: "Motoine", precision: 0.096, recall: 1.0, f1: 0.176 },
  { catchment: "Nyando River", precision: 0.077, recall: 0.2, f1: 0.111 },
  { catchment: "Tana River", precision: 0.108, recall: 0.293, f1: 0.158 },
  {
    catchment: "Nzoia River",
    precision: 0.039,
    recall: 0.4,
    f1: 0.071,
    note: "scoped out of the final system since this run - see below",
  },
];

function pct(value) {
  return value.toFixed(3);
}

export default function LstmAnomaly() {
  const [anomalies, setAnomalies] = useState(null);
  const [error, setError] = useState(null);
  const [flaggedOnly, setFlaggedOnly] = useState(false);

  useEffect(() => {
    get("/api/anomalies/recent", flaggedOnly ? { flagged: "true", limit: 500 } : { limit: 50 })
      .then(setAnomalies)
      .catch((err) => setError(err.message));
  }, [flaggedOnly]);

  return (
    <section>
      <PageHeader
        title="LSTM anomaly model"
        subtitle="Performance from the latest logged training run, not computed live by this dashboard"
      />

      <div className="metric-card-row">
        <MetricCard
          tone="soft"
          label="Precision"
          value={pct(COMBINED.precision)}
          description="Share of flagged days that were real flood days"
        />
        <MetricCard
          tone="soft"
          label="Recall"
          value={pct(COMBINED.recall)}
          valueSuffix={`target ≥ ${PROPOSAL_TARGET.recall}`}
          description="Share of real flood days the model flagged"
        />
        <MetricCard
          tone="deep"
          label="F1-score"
          value={pct(COMBINED.f1)}
          valueSuffix={`target ≥ ${PROPOSAL_TARGET.f1}`}
          badge={{ role: "muted", glyph: "○", label: "Below proposal target" }}
          description="Pooled across catchments, drift-conditional threshold (training-results.md, Phase 9)"
        />
      </div>

      <div className="lstm-panel-stack">
      <div className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Results by catchment</h2>
          <span className="panel-caption">
            All three ERA5 features, narrowed split - the kept feature set (training-results.md, Phase 9/10)
          </span>
        </div>

        <table className="lstm-table">
          <thead>
            <tr>
              <th>Catchment</th>
              <th>Precision</th>
              <th>Recall</th>
              <th>F1-score</th>
              <th aria-hidden="true" />
            </tr>
          </thead>
          <tbody>
            {PER_CATCHMENT.map((row) => (
              <tr key={row.catchment}>
                <td className="lstm-table-strong">{row.catchment}</td>
                <td className="figure">{pct(row.precision)}</td>
                <td className="figure">{pct(row.recall)}</td>
                <td className="figure">{pct(row.f1)}</td>
                <td className="lstm-table-note">{row.note ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <p className="lstm-caveat">
          Nairobi River, Ngong and Motoine still show recall pinned near 1.000 at low precision - a
          validation-to-test drift problem documented in training-results.md, not yet resolved by feature
          selection. The six-catchment, final-feature-set confirmation run (Nzoia removed) is still
          outstanding; see the project checklist.
        </p>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2 className="panel-title">
            {flaggedOnly ? `Flagged days (${anomalies ? anomalies.length : "…"})` : "Recent anomaly scores"}
          </h2>
          <button type="button" onClick={() => {
              setAnomalies(null);
              setFlaggedOnly((v) => !v);
            }}>
            {flaggedOnly ? "Show all recent days" : "Show flagged days only"}
          </button>
          <span className="panel-caption">
            Live LSTM inference output, where it exists (proposal 3.6.4)
          </span>
        </div>

        {error && <p className="error">{error}</p>}

        {anomalies && anomalies.length === 0 && (
          <EmptyState>
            No anomaly scores logged yet - this dashboard's alerts currently come from the stream
            processor's rule-based rules, not live LSTM inference (see Overview).
          </EmptyState>
        )}

        {anomalies && anomalies.length > 0 && (
          <table className="lstm-table">
            <thead>
              <tr>
                <th>Catchment</th>
                <th>Detected</th>
                <th>Anomaly score</th>
                <th>Threshold</th>
                <th>Flagged</th>
              </tr>
            </thead>
            <tbody>
              {anomalies.map((row) => (
                <tr key={row.id}>
                  <td className="lstm-table-strong">{row.catchment}</td>
                  <td className="figure">{new Date(row.detected_at).toLocaleDateString("en-GB", { timeZone: "UTC" })}</td>
                  <td className="figure">{row.anomaly_score.toFixed(3)}</td>
                  <td className="figure">{row.threshold_used.toFixed(3)}</td>
                  <td>{row.is_anomalous ? "Anomalous" : "Normal"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      </div>
    </section>
  );
}
