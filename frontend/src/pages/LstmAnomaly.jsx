import { useEffect, useState } from "react";
import PageHeader from "../components/PageHeader";
import MetricCard from "../components/MetricCard";
import { IconBrain, IconPulse, IconTarget } from "../components/icons";
import OverviewTab from "./lstm/OverviewTab";
import ScoresTab from "./lstm/ScoresTab";
import DayLookupTab from "./lstm/DayLookupTab";
import { get } from "../api";
import "./LstmAnomaly.css";

// The headline scores stay at the top of the page, as they always have, and the
// detail below them is split into three tabs: how the model was measured
// (Overview), the scores themselves (Recent scores), and one chosen day in full
// (Day lookup). Nothing on this page is hardcoded any more - the figures come
// from the deployed model's own evaluation and the scores it has written, and
// which version is running is stated on the Recent scores tab rather than in a
// status bar of its own.
const TABS = [
  { id: "overview", label: "Overview" },
  { id: "scores", label: "Recent scores" },
  { id: "lookup", label: "Day lookup" },
];

// From the proposal's success criteria (3.7), kept on the cards as the bar the
// model is being held to rather than quietly dropped.
const PROPOSAL_TARGET = { f1: 0.7, recall: 0.75 };

// Precision, recall and F1, in the same two filled tones the Overview and
// Administration screens use. Each card shows the count behind its own ratio
// rather than a generic bar: precision is flags that were right out of flags
// made, recall is flood days caught out of flood days there were, and F1 has
// no two counts of its own, so it carries the proposal target instead.
function ScoreCards({ evaluation }) {
  const flags = evaluation.true_positives + evaluation.false_positives;
  return (
    <div className="metric-card-row lstm-metric-row">
      <MetricCard
        tone="soft"
        label="Precision"
        value={evaluation.precision.toFixed(3)}
        glyph={IconTarget}
        segments={[{ amount: evaluation.true_positives, color: "var(--accent-strong)" }]}
        segmentsTotal={flags}
        description={`${evaluation.true_positives} of ${flags} flagged days with a known label were flood days`}
      />
      <MetricCard
        tone="deep"
        label="Recall"
        value={evaluation.recall.toFixed(3)}
        valueSuffix={`target ≥ ${PROPOSAL_TARGET.recall}`}
        glyph={IconPulse}
        segments={[{ amount: evaluation.true_positives, color: "#ffffff" }]}
        segmentsTotal={evaluation.flood_days}
        description={`${evaluation.true_positives} of ${evaluation.flood_days} flood days flagged`}
      />
      <MetricCard
        tone="soft"
        label="F1-score"
        value={evaluation.f1.toFixed(3)}
        valueSuffix={`target ≥ ${PROPOSAL_TARGET.f1}`}
        glyph={IconBrain}
        badge={{ role: "muted", glyph: "○", label: "Below proposal target" }}
        description={`Precision and recall together, at the ${evaluation.threshold.toFixed(3)} flag line`}
      />
    </div>
  );
}

export default function LstmAnomaly() {
  const [tab, setTab] = useState("overview");
  const [model, setModel] = useState(null);
  const [catchments, setCatchments] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([get("/api/anomalies/model"), get("/api/catchments")])
      .then(([modelInfo, list]) => {
        setModel(modelInfo);
        setCatchments(list.map((c) => c.name));
      })
      .catch((err) => setError(err.message));
  }, []);

  return (
    <section>
      <PageHeader
        title="LSTM anomaly model"
        subtitle="The deployed model's own results, the days it has scored, and any day looked up in full"
      />

      {error && <p className="error">{error}</p>}
      {model?.evaluation && <ScoreCards evaluation={model.evaluation} />}

      <div className="panel lstm-panel">
        <nav className="lstm-tabs" aria-label="LSTM views">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              className={tab === t.id ? "active" : ""}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>

        {model && tab === "overview" && <OverviewTab model={model} />}
        {model && tab === "scores" && <ScoresTab catchments={catchments} />}
        {model && tab === "lookup" && <DayLookupTab model={model} catchments={catchments} />}
      </div>
    </section>
  );
}
