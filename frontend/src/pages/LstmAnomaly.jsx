import { useEffect, useState } from "react";
import PageHeader from "../components/PageHeader";
import MetricCard from "../components/MetricCard";
import EmptyState from "../components/EmptyState";
import { get } from "../api";
import "./LstmAnomaly.css";

// Confirmed, reproducible numbers from training-results.md's "Confirmed
// six-catchment result, Dataset_labels_v8.csv" section: the LSTM
// autoencoder (the system's actual production model - see
// decisions-and-learnings.md), src/train.py's own plain per-catchment
// method, the method to lead with. The three-method comparison and the
// Random Forest / XGBoost rows below are current as of this week's
// Dataset_labels_v9.csv investigation (training-results.md / this page's
// own update). These are static content, not fetched from the backend -
// there is no live model-metrics endpoint. Update this block once a new
// training run is logged.
const COMBINED = { precision: 0.062, recall: 0.637, f1: 0.113 };

const PER_CATCHMENT = [
  { catchment: "Nairobi River", precision: 0.045, recall: 1.0, f1: 0.087 },
  { catchment: "Mathare", precision: 0.209, recall: 0.9, f1: 0.34 },
  { catchment: "Ngong", precision: 0.1, recall: 0.875, f1: 0.179 },
  { catchment: "Motoine", precision: 0.047, recall: 1.0, f1: 0.089 },
  {
    catchment: "Nyando River",
    precision: 0.0,
    recall: 0.0,
    f1: 0.0,
    note: "4 widely separated flood events since 2010; no standard split gives it validation-period data",
  },
  {
    catchment: "Tana River",
    precision: 0.09,
    recall: 0.415,
    f1: 0.148,
    note: "floods here run far longer on average (~43 days) than the other rivers (~9 days)",
  },
];

// Every method/model tried against this problem, pooled across
// catchments. The three LSTM rows are the autoencoder scored three
// different ways (training-results.md); Random Forest and XGBoost are
// a separate model family tried this week on the same engineered
// features (src/model_selection.py). The LSTM rows are the last fully
// confirmed, reproducible run (v8); the "v9" note is this week's
// corrected flood register, re-scored by F1 only so far. Random Forest
// and XGBoost were run directly on v9.
const MODEL_COMPARISON = [
  {
    model: "LSTM, simple per-catchment",
    precision: 0.062,
    recall: 0.637,
    f1: 0.113,
    note: "Headline method; v9 (corrected register): 0.117",
  },
  {
    model: "LSTM, drift-conditional pooled",
    precision: 0.141,
    recall: 0.475,
    f1: 0.217,
    note: "v9: 0.189",
  },
  {
    model: "LSTM, cross-catchment consensus",
    f1: 0.412,
    note: "Best result of any method; v9: 0.356. Nyando never contributes a flag on its own",
  },
  {
    model: "Random Forest",
    precision: 0.227,
    recall: 0.519,
    f1: 0.316,
    note: "v9. Clearly ahead of the LSTM's plain and pooled methods",
  },
  {
    model: "XGBoost",
    precision: 0.092,
    recall: 0.914,
    f1: 0.168,
    note: "v9. Threshold not yet well tuned; over-flags broadly",
  },
];

function pct(value) {
  return value === undefined ? "-" : value.toFixed(3);
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
          description="Share of flagged days that were real flood days"
        />
        <MetricCard
          tone="soft"
          label="Recall"
          value={pct(COMBINED.recall)}
          description="Share of real flood days the model flagged"
        />
        <MetricCard
          tone="deep"
          label="F1-score"
          value={pct(COMBINED.f1)}
          description="Balance of precision and recall, plain per-catchment method"
        />
      </div>

      <div className="lstm-panel-stack">
      <div className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Results by catchment</h2>
          <span className="panel-caption">
            LSTM autoencoder, plain per-catchment threshold - v8 dataset, confirmed reproducible run
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
          Every flood day is caught on the four Nairobi-area rivers, at precision 0.05-0.21. The pooled
          figure is held down by Nyando River, where the problem is the data rather than the model (see
          the note above, and the model comparison below). Nairobi River, Ngong and Motoine over-flag
          because 2024-2025 is measurably wetter than the years the model learned "normal" from.
        </p>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Model comparison</h2>
          <span className="panel-caption">
            Every method/model tried on this problem, pooled across catchments, 2024-2025 test set
          </span>
        </div>

        <table className="lstm-table">
          <thead>
            <tr>
              <th>Model</th>
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
                <td className="figure">{pct(row.precision)}</td>
                <td className="figure">{pct(row.recall)}</td>
                <td className="figure">{pct(row.f1)}</td>
                <td className="lstm-table-note">{row.note ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <p className="lstm-caveat">
          <strong>About Random Forest:</strong> unlike the autoencoder, which only learns what a normal
          day looks like and flags anything unusual, Random Forest is shown real flood and non-flood days
          directly and learns to tell them apart. It builds many independent decision trees on random
          subsets of the data and features, then averages their votes. It only sees one day's features at
          a time, not the autoencoder's 14-day window, but those features already include rolling and
          trend versions of rainfall and discharge. It currently scores clearly higher than the LSTM's
          plain and pooled methods, though not as high as the LSTM's cross-catchment consensus method.
          XGBoost, the other model tried, underperforms both so far, most likely because its threshold is
          not yet properly tuned for how rare flood days are in this data, not because gradient boosting
          is unsuited to the problem.
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
