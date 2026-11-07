import { useEffect, useState } from "react";
import EmptyState from "../../components/EmptyState";
import { get } from "../../api";

// How the headline scores above were arrived at: four figures, each drawn as
// the shape it actually is - a share of events caught, a rate per year, a
// score on a nought-to-one scale, and a split between measured and unknown
// days - and filled in the same two tones the Overview and Administration
// screens use. No live fetch of its own: everything comes from the model card
// the page already loaded, which reads models/flood_lstm/evaluation.json,
// saved beside the weights, so retraining updates this rather than needing
// numbers edited in here.

const MONTH_INITIAL = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
// Kenya's two wet seasons, shaded behind the months strip. Nothing is computed
// from them; they are there so the pattern in the bars can be read at a glance.
const LONG_RAINS = [2, 3, 4];
const SHORT_RAINS = [9, 10, 11];

function formatDay(iso) {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { timeZone: "UTC" });
}

// A ring is the honest shape for "x of y caught": the gap is as readable as
// the fill, which a bar of its own does not give you at this size.
function Ring({ value, total }) {
  const radius = 26;
  const circumference = 2 * Math.PI * radius;
  const filled = total > 0 ? value / total : 0;
  return (
    <svg className="lstm-stat-ring" viewBox="0 0 64 64" role="presentation">
      <circle cx="32" cy="32" r={radius} className="lstm-stat-ring-track" />
      <circle
        cx="32"
        cy="32"
        r={radius}
        className="lstm-stat-ring-fill"
        strokeDasharray={`${circumference * filled} ${circumference}`}
      />
      <text x="32" y="36" className="lstm-stat-ring-text">
        {Math.round(filled * 100)}%
      </text>
    </svg>
  );
}

// Twelve marks for twelve months, so "3.3 a year" reads as how often rather
// than as a bare number.
function Months({ rate }) {
  const whole = Math.floor(rate);
  return (
    <div className="lstm-stat-months" role="presentation">
      {Array.from({ length: 12 }, (_, i) => (
        <span
          key={i}
          className={`lstm-stat-month${i < whole ? " lstm-stat-month--on" : ""}${
            i === whole && rate % 1 > 0 ? " lstm-stat-month--part" : ""
          }`}
        />
      ))}
    </div>
  );
}

function Scale({ value }) {
  return (
    <div className="lstm-stat-scale">
      <div className="lstm-stat-scale-track">
        <span className="lstm-stat-scale-fill" style={{ width: `${value * 100}%` }} />
      </div>
      <div className="lstm-stat-scale-ticks">
        <span>0</span>
        <span>0.5</span>
        <span>1</span>
      </div>
    </div>
  );
}

function Split({ measured, total }) {
  return (
    <div className="lstm-stat-split">
      <div className="lstm-stat-scale-track">
        <span className="lstm-stat-scale-fill" style={{ width: `${(measured / total) * 100}%` }} />
      </div>
      <div className="lstm-stat-split-key">
        <span>
          <i className="lstm-stat-swatch lstm-stat-swatch--on" />
          labelled
        </span>
        <span>
          <i className="lstm-stat-swatch" />
          {(total - measured).toLocaleString()} unknown
        </span>
      </div>
    </div>
  );
}

// When the model actually fired, month by month across the measured period.
// One short bar chart rather than another figure: it shows at a glance that the
// flags fall in Nairobi's two wet seasons rather than scattered through the
// year, which is the thing a reader most wants to check about a flood model.
function WhenItFlagged({ evaluation }) {
  const [counts, setCounts] = useState(null);
  const [error, setError] = useState(null);
  const [firstYear, lastYear] = [
    Number(evaluation.test_period[0].slice(0, 4)),
    Number(evaluation.test_period[1].slice(0, 4)),
  ];

  useEffect(() => {
    get("/api/anomalies/scores", { flagged: "true", limit: 500 })
      .then((result) => {
        const tally = {};
        result.rows.forEach((row) => {
          const key = row.day.slice(0, 7);
          tally[key] = (tally[key] ?? 0) + 1;
        });
        setCounts(tally);
      })
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!counts) return null;

  const years = [];
  for (let year = firstYear; year <= lastYear; year += 1) years.push(year);
  const peak = Math.max(1, ...Object.values(counts));

  return (
    <>
      <div className="lstm-section-head">
        <h2 className="panel-title">When it flagged</h2>
        <span className="panel-caption">
          {evaluation.flagged_total} flagged days, by month, all three catchments
        </span>
      </div>

      <div className="lstm-when">
        {years.map((year) => (
          <div key={year} className="lstm-when-year">
            <div className="lstm-when-bars">
              {MONTH_INITIAL.map((initial, month) => {
                const key = `${year}-${String(month + 1).padStart(2, "0")}`;
                const count = counts[key] ?? 0;
                const wet = LONG_RAINS.includes(month) || SHORT_RAINS.includes(month);
                return (
                  <div
                    key={key}
                    className={`lstm-when-month${wet ? " lstm-when-month--wet" : ""}`}
                    title={`${count} flagged day${count === 1 ? "" : "s"} in ${key}`}
                  >
                    <span className="lstm-when-count">{count || ""}</span>
                    <span className="lstm-when-bar" style={{ height: `${(count / peak) * 100}%` }} />
                    <span className="lstm-when-initial">{initial}</span>
                  </div>
                );
              })}
            </div>
            <div className="lstm-when-year-label figure">{year}</div>
          </div>
        ))}
      </div>

      <p className="lstm-when-key">
        <span>
          <i className="lstm-when-swatch" />
          long rains, March to May, and short rains, October to December
        </span>
      </p>
    </>
  );
}

export default function OverviewTab({ model }) {
  const evaluation = model.evaluation;

  if (!evaluation) {
    return (
      <EmptyState>
        No evaluation saved for this model version yet (models/flood_lstm/evaluation.json).
      </EmptyState>
    );
  }

  return (
    <div className="lstm-tab">
      <div className="lstm-section-head">
        <h2 className="panel-title">How {model.name} was measured</h2>
        <span className="panel-caption">
          {formatDay(evaluation.test_period[0])} to {formatDay(evaluation.test_period[1])}, years the model
          never trained on
        </span>
      </div>

      <div className="lstm-stat-grid">
        <div className="lstm-stat lstm-stat--soft lstm-stat--ring">
          <div>
            <div className="lstm-stat-label">Events caught</div>
            <div className="lstm-stat-value figure">
              {evaluation.events_detected}
              <span className="lstm-stat-of">of {evaluation.events_total}</span>
            </div>
            <p className="lstm-stat-note">events with at least one flag</p>
          </div>
          <Ring value={evaluation.events_detected} total={evaluation.events_total} />
        </div>

        <div className="lstm-stat lstm-stat--deep">
          <div className="lstm-stat-label">False alarms</div>
          <div className="lstm-stat-value figure">
            {evaluation.false_alarms_per_catchment_year.toFixed(1)}
            <span className="lstm-stat-of">days a year</span>
          </div>
          <Months rate={evaluation.false_alarms_per_catchment_year} />
          <p className="lstm-stat-note">per catchment</p>
        </div>

        <div className="lstm-stat lstm-stat--soft">
          <div className="lstm-stat-label">Average precision</div>
          <div className="lstm-stat-value figure">{evaluation.average_precision.toFixed(3)}</div>
          <Scale value={evaluation.average_precision} />
          <p className="lstm-stat-note">across all flag lines</p>
        </div>

        <div className="lstm-stat lstm-stat--deep">
          <div className="lstm-stat-label">Days measured</div>
          <div className="lstm-stat-value figure">
            {evaluation.days_with_label.toLocaleString()}
            <span className="lstm-stat-of">of {evaluation.days_scored.toLocaleString()}</span>
          </div>
          <Split measured={evaluation.days_with_label} total={evaluation.days_scored} />
          <p className="lstm-stat-note">days the audit settled</p>
        </div>
      </div>

      <WhenItFlagged evaluation={evaluation} />
    </div>
  );
}
