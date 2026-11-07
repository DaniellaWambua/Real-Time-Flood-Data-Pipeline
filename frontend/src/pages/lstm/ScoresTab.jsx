import { useEffect, useState } from "react";
import EmptyState from "../../components/EmptyState";
import StatusChip from "../../components/StatusChip";
import { severityRole } from "../../statusRoles";
import { downloadCsv } from "../../csv";
import { get } from "../../api";

// The scores list, queryable: one catchment or all, a date range, and flagged
// days only. GET /api/anomalies/scores returns the matching total alongside the
// page, so "Load more" knows when there is nothing left to fetch.
const PAGE_SIZE = 25;

const PERIODS = [
  { id: "30", label: "Last 30 days" },
  { id: "90", label: "Last 90 days" },
  { id: "365", label: "Last year" },
  { id: "", label: "All time" },
];

function formatDay(iso) {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { timeZone: "UTC" });
}

// Periods are counted back from the last day scored, not from today: this is a
// historical replay, so "last 30 days" means the 30 most recent scored days.
function rangeFrom(period, lastDay) {
  if (!period || !lastDay) return "";
  const end = new Date(`${lastDay}T00:00:00Z`);
  end.setUTCDate(end.getUTCDate() - Number(period));
  return end.toISOString().slice(0, 10);
}

export default function ScoresTab({ catchments }) {
  const [filters, setFilters] = useState({ catchment: "", period: "30", flagged: false });
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [data, setData] = useState(null);
  const [lastDay, setLastDay] = useState(null);
  const [modelName, setModelName] = useState("");
  const [error, setError] = useState(null);

  useEffect(() => {
    get("/api/anomalies/model")
      .then((model) => {
        setLastDay(model.live?.last_day ?? null);
        setModelName(model.name);
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (lastDay === null) return undefined;
    let current = true;
    get("/api/anomalies/scores", {
      catchment: filters.catchment,
      from: rangeFrom(filters.period, lastDay),
      flagged: filters.flagged ? "true" : "",
      limit,
    })
      .then((result) => current && setData(result))
      .catch((err) => current && setError(err.message));
    return () => {
      current = false;
    };
  }, [filters, limit, lastDay]);

  function updateFilter(key, value) {
    setData(null);
    setLimit(PAGE_SIZE);
    setFilters((f) => ({ ...f, [key]: value }));
  }

  function exportCsv() {
    downloadCsv(
      "anomaly-scores",
      ["Date", "Catchment", "Score", "Threshold", "Flagged", "Alert"],
      (data?.rows ?? []).map((row) => [
        row.day,
        row.catchment,
        Number(row.anomaly_score).toFixed(3),
        Number(row.threshold_used).toFixed(3),
        row.is_anomalous ? "yes" : "no",
        row.alert_severity ?? "",
      ]),
    );
  }

  const rows = data?.rows ?? [];

  return (
    <div className="lstm-tab">
      <div className="lstm-querybar">
        <div className="lstm-seg">
          <button
            type="button"
            className={filters.catchment === "" ? "active" : ""}
            onClick={() => updateFilter("catchment", "")}
          >
            All
          </button>
          {catchments.map((name) => (
            <button
              key={name}
              type="button"
              className={filters.catchment === name ? "active" : ""}
              onClick={() => updateFilter("catchment", name)}
            >
              {name}
            </button>
          ))}
        </div>

        <label className="pill-select">
          <span className="pill-select-key">Period</span>
          <select value={filters.period} onChange={(e) => updateFilter("period", e.target.value)}>
            {PERIODS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </label>

        <label className="lstm-switch">
          <input
            type="checkbox"
            checked={filters.flagged}
            onChange={(e) => updateFilter("flagged", e.target.checked)}
          />
          Flagged days only
        </label>

        <span className="lstm-querybar-count">
          {data ? `${data.total.toLocaleString()} day${data.total === 1 ? "" : "s"} match` : "Loading…"}
        </span>
        <button type="button" onClick={exportCsv} disabled={rows.length === 0}>
          Export CSV
        </button>
      </div>

      {modelName && lastDay && (
        <p className="lstm-source-note">
          Scored by <strong>{modelName}</strong>, up to {formatDay(lastDay)}
        </p>
      )}

      {error && <p className="error">{error}</p>}
      {data && rows.length === 0 && <EmptyState>No scores match these filters.</EmptyState>}

      {rows.length > 0 && (
        <>
          <div className="lstm-scroll">
            <table className="lstm-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Catchment</th>
                  <th>Score</th>
                  <th>Flagged</th>
                  <th>Alert</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td className="figure">{formatDay(row.day)}</td>
                    <td className="lstm-table-strong">{row.catchment}</td>
                    <td className="figure">
                      {Number(row.anomaly_score).toFixed(3)}
                      <span className="lstm-bar" aria-hidden="true">
                        <span style={{ width: `${Math.min(Number(row.anomaly_score), 1) * 100}%` }} />
                      </span>
                    </td>
                    <td>{row.is_anomalous ? "Yes" : <span className="lstm-dash">No</span>}</td>
                    <td>
                      {row.alert_severity ? (
                        <StatusChip role={severityRole(row.alert_severity)} label={row.alert_severity} />
                      ) : (
                        <span className="lstm-dash">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="lstm-pager">
            <span>
              Showing {rows.length.toLocaleString()} of {data.total.toLocaleString()}
            </span>
            {rows.length < data.total && (
              <button type="button" onClick={() => setLimit((l) => l + PAGE_SIZE)}>
                Load more
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
