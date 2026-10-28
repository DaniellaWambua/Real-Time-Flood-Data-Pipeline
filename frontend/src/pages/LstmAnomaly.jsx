import { useEffect, useState } from "react";
import PageHeader from "../components/PageHeader";
import MetricCard from "../components/MetricCard";
import EmptyState from "../components/EmptyState";
import { get } from "../api";
import "./LstmAnomaly.css";

// Real numbers from reports/model_selection/v7/lstm.json (training-results.md,
// Phase 12): the supervised LSTM classifier, averaged over five seeds, on
// Dataset_labels_v7.csv (six catchments, all eight features). It was chosen
// over a 1D CNN, random forest and gradient boosting on cross-validated F1
// (2015-2023), then scored once on the 2024-2025 test set, which is what is
// shown here. PREVIOUS is the LSTM autoencoder it replaced, on the same test
// period. These are static content, not fetched from the backend - there is
// no live model-metrics endpoint, and these numbers only change when a new
// training run is logged. Update this block once a later run lands.
const COMBINED = { precision: 0.153, recall: 0.58, f1: 0.242 };

const PREVIOUS = { precision: 0.113, recall: 0.541, f1: 0.187 };

const PER_CATCHMENT = [
  { catchment: "Nairobi River", precision: 0.229, recall: 1.0, f1: 0.372 },
  { catchment: "Mathare", precision: 0.185, recall: 1.0, f1: 0.312 },
  { catchment: "Ngong", precision: 0.14, recall: 1.0, f1: 0.246 },
  { catchment: "Motoine", precision: 0.163, recall: 1.0, f1: 0.281 },
  {
    catchment: "Nyando River",
    precision: 0.0,
    recall: 0.0,
    f1: 0.0,
    note: "April-May 2024 floods missing from the flood register",
  },
  {
    catchment: "Tana River",
    precision: 0.149,
    recall: 0.31,
    f1: 0.202,
    note: "discharge point reads zero on 85% of days",
  },
];

// TEMPORARY: every model from the same comparison run, so the alternatives
// can be seen side by side while fine-tuning continues. Numbers from
// reports/model_selection/v7/*.json. Delete this block and the "Model
// comparison" panel below once the final model is settled.
const MODEL_COMPARISON = [
  { model: "LSTM, 5-seed average", cvF1: 0.333, precision: 0.153, recall: 0.58, f1: 0.242, note: "Selected" },
  { model: "1D CNN, 5-seed average", cvF1: 0.243, precision: 0.259, recall: 0.519, f1: 0.346 },
  { model: "Random forest", cvF1: 0.2, precision: 0.244, recall: 0.79, f1: 0.373 },
  { model: "Gradient boosting", cvF1: 0.166, precision: 0.147, recall: 0.815, f1: 0.25 },
  { model: "LSTM + random forest", cvF1: 0.281, precision: 0.23, recall: 0.494, f1: 0.314 },
  { model: "LSTM autoencoder (before)", precision: 0.113, recall: 0.541, f1: 0.187, note: "Replaced" },
];

function pct(value) {
  return value.toFixed(3);
}

export default function LstmAnomaly() {
  const [anomalies, setAnomalies] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    get("/api/anomalies/recent", { limit: 50 })
      .then(setAnomalies)
      .catch((err) => setError(err.message));
  }, []);

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
          description={`Share of flagged days that were real flood days (was ${pct(PREVIOUS.precision)})`}
        />
        <MetricCard
          tone="soft"
          label="Recall"
          value={pct(COMBINED.recall)}
          description={`Share of real flood days the model flagged (was ${pct(PREVIOUS.recall)})`}
        />
        <MetricCard
          tone="deep"
          label="F1-score"
          value={pct(COMBINED.f1)}
          description={`Balance of precision and recall (was ${pct(PREVIOUS.f1)})`}
        />
      </div>

      <div className="lstm-panel-stack">
      <div className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Results by catchment</h2>
          <span className="panel-caption">
            LSTM classifier, 30-day window, averaged over five seeds - v7 dataset (training-results.md, Phase 12)
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
          Every flood day is caught on the four Nairobi-area rivers, at precision 0.14-0.23. The pooled
          figures are held down by Nyando River and Tana River, where the problem is the data rather than
          the model (see the notes above). The 1D CNN and random forest scored higher on this test set but
          lower in cross-validation, so the LSTM stays the selected model.
        </p>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Model comparison (temporary)</h2>
          <span className="panel-caption">
            All models from the same run, pooled across catchments - v7 dataset, 2024-2025 test set
          </span>
        </div>

        <table className="lstm-table">
          <thead>
            <tr>
              <th>Model</th>
              <th>CV F1</th>
              <th>Precision</th>
              <th>Recall</th>
              <th>F1-score</th>
              <th aria-hidden="true" />
            </tr>
          </thead>
          <tbody>
            {MODEL_COMPARISON.map((row) => (
              <tr key={row.model}>
                <td className="lstm-table-strong">{row.model}</td>
                <td className="figure">{row.cvF1 === undefined ? "-" : pct(row.cvF1)}</td>
                <td className="figure">{pct(row.precision)}</td>
                <td className="figure">{pct(row.recall)}</td>
                <td className="figure">{pct(row.f1)}</td>
                <td className="lstm-table-note">{row.note ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <p className="lstm-caveat">
          CV F1 is the cross-validated score on 2015-2023 that the model was chosen by; the other three
          columns are the 2024-2025 test set, which was not used to choose. The autoencoder predates this
          comparison, so it has no CV F1.
        </p>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Recent anomaly scores</h2>
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
                  <td className="figure">{new Date(row.detected_at).toLocaleString()}</td>
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
