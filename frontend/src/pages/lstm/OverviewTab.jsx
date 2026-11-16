import { useEffect, useState } from "react";
import EmptyState from "../../components/EmptyState";
import { get } from "../../api";

// When the deployed model flagged, month by month over the held-out years. Its results are on the cards
// above the tabs, read from evaluation.json, so retraining updates them without editing this file.

const MONTH_INITIAL = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
// Kenya's two wet seasons, shaded behind the months strip. Nothing is computed
// from them; they are there so the pattern in the bars can be read at a glance.
const LONG_RAINS = [2, 3, 4];
const SHORT_RAINS = [9, 10, 11];

// Flags by month, to show they fall in Nairobi's two wet seasons.
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
          {evaluation.flagged_total} flagged days by month, all three catchments, {firstYear} to {lastYear}: years
          the model never trained on
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
          <i className="lstm-when-swatch lstm-when-swatch--bar" />
          flagged days in the month
        </span>
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
      <WhenItFlagged evaluation={evaluation} />
    </div>
  );
}
