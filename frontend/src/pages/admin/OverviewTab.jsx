import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import StatusChip from "../../components/StatusChip";
import MetricCard from "../../components/MetricCard";
import { IconBell, IconBrain, IconDatabase, IconDrop, IconMap, IconUsers } from "../../components/icons";
import { connectionRole } from "../../statusRoles";
import { get } from "../../api";

// GET /api/admin/stats. Each card carries the one breakdown that says what
// state it is in, not just how many rows there are, and the row alternates the
// two filled tones the Overview screen uses (Pale Ice Blue and Forest Green) so
// Administration reads as the same system rather than a second palette.
function formatDay(iso) {
  return iso ? new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { timeZone: "UTC" }) : "no data yet";
}

function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function StatsRow({ stats }) {
  const cards = [
    {
      label: "Users",
      value: stats.users,
      glyph: IconUsers,
      description: `${stats.users - stats.users_pending - stats.users_inactive} active, ${plural(stats.users_pending, "invite")} pending`,
    },
    {
      label: "Catchments",
      value: stats.catchments,
      glyph: IconMap,
      description: `monitored, ${stats.catchments_inactive} kept as history`,
    },
    {
      label: "Data sources",
      value: stats.data_sources,
      glyph: IconDatabase,
      description:
        stats.sources_connected === stats.data_sources
          ? "all connected"
          : `${stats.sources_connected} connected, ${stats.data_sources - stats.sources_connected} down`,
    },
    {
      label: "Readings",
      value: stats.readings.toLocaleString(),
      glyph: IconDrop,
      description: `latest ${formatDay(stats.readings_last_day)}`,
    },
    {
      label: "Alerts",
      value: stats.alerts.toLocaleString(),
      glyph: IconBell,
      description: `${stats.alerts_open} open, ${stats.alerts_acknowledged} acknowledged`,
    },
    {
      label: "Anomaly results",
      value: stats.anomalies.toLocaleString(),
      glyph: IconBrain,
      description: `${stats.anomalies_flagged} flagged by the model`,
    },
  ];

  return (
    <div className="metric-card-row admin-metric-row">
      {cards.map((card, index) => (
        <MetricCard
          key={card.label}
          tone={index % 2 === 0 ? "soft" : "deep"}
          label={card.label}
          value={card.value}
          description={card.description}
          glyph={card.glyph}
        />
      ))}
    </div>
  );
}

function StatsRowSkeleton() {
  return (
    <div className="metric-card-row admin-metric-row" aria-hidden="true">
      {Array.from({ length: 6 }, (_, index) => (
        <div
          key={index}
          className={`metric-card metric-card--${index % 2 === 0 ? "soft" : "deep"} metric-card--loading`}
        >
          <div className="metric-card-label">&nbsp;</div>
          <div className="metric-card-value">&nbsp;</div>
          <p className="metric-card-description">&nbsp;</p>
        </div>
      ))}
    </div>
  );
}

// GET /api/alerts/summary and /api/alerts/trend taught the same lesson
// here: a database overview is a glance, not a page of its own, so
// this reads one small endpoint rather than totalling up what the
// other panels already fetched.
function StatsPanel() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    get("/api/admin/stats")
      .then(setStats)
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  // Hold the row's place while the counts load. Returning nothing here let the
  // Data sources panel render first and the cards drop in above it a moment
  // later, which read as the page reordering itself.
  if (!stats) return <StatsRowSkeleton />;

  return <StatsRow stats={stats} />;
}

// GET /api/sources has no matching PATCH (it is historical replay
// data, see routes_dashboard.py's list_sources()), so, same as
// Alerts.jsx's read-only table, there is nothing real for a
// "Reconnect" button to do yet and one is not added here - only
// "View stream" is a genuine link, to the Data stream page this data
// actually feeds.
function SourcesPanel() {
  const [sources, setSources] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    get("/api/sources")
      .then(setSources)
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!sources) return null;

  const connectedCount = sources.filter((s) => s.connection_status === "connected").length;

  return (
    <div className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Data sources</h2>
        <span className="panel-caption">
          {connectedCount} of {sources.length} connected
        </span>
      </div>

      {/* A glanceable status grid above the detail table, per
          Daniella's request for something closer to how Kubernetes
          shows node/pod health - one small tile per source with its
          live connection status up front, rather than only a text
          row buried in a wider table. Same /api/sources data as the
          table below, not a second fetch or a separate concept. */}
      <div className="pipeline-health-grid">
        {sources.map((source) => (
          <div key={source.id} className="pipeline-health-tile">
            <div className="pipeline-health-tile-header">
              <span
                className={`pipeline-health-dot pipeline-health-dot--${connectionRole(source.connection_status)}`}
                aria-hidden="true"
              />
              <span className="pipeline-health-tile-name">{source.name}</span>
            </div>
            <StatusChip role={connectionRole(source.connection_status)} label={source.connection_status} />
            <dl className="pipeline-health-tile-stats">
              <div>
                <dt>Last ingested</dt>
                <dd className="figure">
                  {source.last_ingested_at ? new Date(source.last_ingested_at).toLocaleString() : "No data yet"}
                </dd>
              </div>
              <div>
                <dt>Records</dt>
                <dd className="figure">{source.record_count.toLocaleString()}</dd>
              </div>
            </dl>
          </div>
        ))}
      </div>

      <table className="admin-table">
        <thead>
          <tr>
            <th>Source</th>
            <th>Type</th>
            <th>Status</th>
            <th>Last ingested</th>
            <th>Records</th>
            <th>Added</th>
            <th aria-hidden="true" />
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.id}>
              <td className="admin-table-strong">{source.name}</td>
              <td>{source.source_type}</td>
              <td>
                <StatusChip
                  role={connectionRole(source.connection_status)}
                  label={source.connection_status}
                />
              </td>
              {/* This is historical replay data, not a live feed (see
                  routes_dashboard.py's list_sources()), so this is a
                  record of when ingestion last actually happened, not a
                  real-time freshness check against wall-clock time. */}
              <td className="figure">
                {source.last_ingested_at
                  ? new Date(source.last_ingested_at).toLocaleString()
                  : "No data yet"}
              </td>
              <td className="figure">{source.record_count.toLocaleString()}</td>
              <td className="figure">{new Date(source.created_at).toLocaleDateString()}</td>
              <td className="admin-table-link-cell">
                {source.connection_status === "connected" ? (
                  <Link to="/data-stream" className="admin-stream-link">
                    View stream
                  </Link>
                ) : (
                  // Visual-only, matching the Alerts page's Acknowledge/
                  // Resolve precedent: GET /api/sources has no matching
                  // PATCH, so there is nothing real behind a reconnect
                  // action yet. Shown disabled with an explanatory title
                  // rather than left out, since the reference layout
                  // always shows one of these two controls per row.
                  <button
                    type="button"
                    className="admin-reconnect-button"
                    disabled
                    title="Not available yet - this data source has no live reconnect endpoint"
                  >
                    Reconnect
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Administration's Overview tab: database counts and data source health.
export default function OverviewTab() {
  return (
    <>
      <StatsPanel />
      <div className="admin-panel-stack">
        <SourcesPanel />
      </div>
    </>
  );
}
