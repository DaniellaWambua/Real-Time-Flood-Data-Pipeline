import { useEffect, useState } from "react";
import PageHeader from "../components/PageHeader";
import MetricCard from "../components/MetricCard";
import { IconBrain, IconPulse, IconTarget } from "../components/icons";
import OverviewTab from "./lstm/OverviewTab";
import ScoresTab from "./lstm/ScoresTab";
import DayLookupTab from "./lstm/DayLookupTab";
import { get } from "../api";
import "./LstmAnomaly.css";

// Headline scores at the top, then three tabs. All figures come from the deployed model.
const TABS = [
  { id: "overview", label: "Overview" },
  { id: "scores", label: "Recent scores" },
  { id: "lookup", label: "Day lookup" },
];

// The deployed model's event-level results on the held-out years: what an officer sees as one
// warning per flood, rather than one score per day.
function ScoreCards({ evaluation }) {
  const realEpisodes = evaluation.alarm_episodes - evaluation.false_alarm_episodes;
  return (
    <div className="metric-card-row lstm-metric-row">
      <MetricCard
        tone="soft"
        label="Floods detected"
        value={evaluation.events_detected}
        valueSuffix={`of ${evaluation.events_total}`}
        glyph={IconTarget}
        segments={[{ amount: evaluation.events_detected, color: "var(--accent-strong)" }]}
        segmentsTotal={evaluation.events_total}
        description="flood events with at least one alarm"
      />
      <MetricCard
        tone="deep"
        label="Alarms that were real"
        value={`${Math.round(evaluation.event_precision * 100)}%`}
        glyph={IconPulse}
        segments={[{ amount: realEpisodes, color: "#ffffff" }]}
        segmentsTotal={evaluation.alarm_episodes}
        description={`${realEpisodes} of ${evaluation.alarm_episodes} alarm periods matched a flood`}
      />
      <MetricCard
        tone="soft"
        label="False alarms"
        value={evaluation.false_episodes_per_catchment_year.toFixed(1)}
        valueSuffix="per catchment a year"
        glyph={IconBrain}
        description="alarm periods that matched no flood"
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
        title="LSTM flood model"
        subtitle="The deployed model's results on 2024 and 2025, the days it has scored, and any day looked up in full"
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
