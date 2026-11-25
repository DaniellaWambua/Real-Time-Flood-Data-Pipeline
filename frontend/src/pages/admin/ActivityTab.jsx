import { useEffect, useState } from "react";
import Avatar from "../../components/Avatar";
import StatusChip from "../../components/StatusChip";
import EmptyState from "../../components/EmptyState";
import { roleLabel } from "../../roleLabel";
import { severityRole } from "../../statusRoles";
import { downloadCsv } from "../../csv";
import { get } from "../../api";
import "./ActivityTab.css";

// Each area uses the layout that suits its events: tables for many similar entries,
// feeds for fewer actions people read as sentences.
const AREAS = [
  { id: "sign_in", label: "Sign-ins and security", layout: "table" },
  { id: "accounts", label: "User accounts", layout: "feed" },
  { id: "alerts", label: "Alerts", layout: "feed" },
  { id: "pipeline", label: "Data pipeline", layout: "table" },
];
const PERIODS = [
  { id: "1d", label: "Last 24 hours" },
  { id: "7d", label: "Last 7 days" },
  { id: "30d", label: "Last 30 days" },
  { id: "all", label: "All time" },
];
const EMPTY = {
  sign_in: "No sign-ins in this period.",
  accounts: "No account changes in this period.",
  alerts: "No alerts were acknowledged or resolved in this period.",
  pipeline: "No readings were rejected in this period.",
};
const PAGE = 50;

// Sign-in events: label and outcome
const SIGN_IN = {
  login_success: ["Signed in", "success"],
  login_failure: ["Failed sign-in", "failed"],
  login_password_ok_awaiting_totp: ["Password accepted, code requested", "progress"],
  login_password_ok_awaiting_2fa_setup: ["Password accepted, 2FA setup started", "progress"],
  totp_enabled: ["Turned on two-factor sign-in", "success"],
  totp_disabled: ["Turned off two-factor sign-in", "progress"],
  password_reset_completed: ["Chose a new password", "success"],
  password_changed: ["Changed their password", "success"],
  password_change_failure: ["Failed password change", "failed"],
  logout: ["Signed out on every device", "success"],
};
const OUTCOME = { success: ["Success", "good"], failed: ["Failed", "critical"], progress: ["In progress", "active"] };

function formatTime(iso) {
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatClock(iso) {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

// Flood days are stored as midnight UTC, so they are read in UTC
function formatDay(iso) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

function dayHeading(iso) {
  const day = new Date(iso).toDateString();
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (day === today.toDateString()) return "Today";
  if (day === yesterday.toDateString()) return "Yesterday";
  return new Date(iso).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

function pipelineParts(detail) {
  const m = (detail ?? "").match(/^(.+?) (\d{4}-\d{2}-\d{2}): (.+)$/);
  return m ? { catchment: m[1], day: m[2], reason: m[3] } : { catchment: "—", day: "", reason: detail ?? "" };
}

// A plain-language sentence for a user-account event
function accountSentence(row) {
  const who = <strong>{row.actor ?? "Someone"}</strong>;
  const d = row.detail ?? "";
  let m;
  switch (row.action) {
    case "user_invited":
      m = d.match(/^(\S+) <([^>]+)> \((\w+)\)$/);
      return m ? <>{who} invited <strong>{m[1]}</strong> ({m[2]}) as {roleLabel(m[3])}</> : <>{who} invited {d}</>;
    case "user_invite_resent":
      return <>{who} resent the invite to <strong>{d}</strong></>;
    case "user_activated":
      return <>{who} activated their account</>;
    case "user_role_changed":
      m = d.match(/^(\S+) -> (\w+)$/);
      return m ? <>{who} changed <strong>{m[1]}</strong>&rsquo;s role to {roleLabel(m[2])}</> : <>{who} changed a role ({d})</>;
    case "user_deactivated":
      return <>{who} deactivated <strong>{d}</strong></>;
    case "user_reactivated":
      return <>{who} reactivated <strong>{d}</strong></>;
    case "user_details_changed":
      return <>{who} edited <strong>{d}</strong>&rsquo;s details</>;
    case "user_email_changed":
      m = d.match(/^(\S+) -> (\S+)$/);
      return m ? <>{who} changed <strong>{m[1]}</strong>&rsquo;s email to {m[2]}</> : <>{who} changed an email ({d})</>;
    case "user_2fa_reset":
      return <>{who} reset <strong>{d}</strong>&rsquo;s two-factor sign-in</>;
    case "password_reset_sent":
      return <>{who} sent <strong>{d}</strong> a password reset link</>;
    case "user_created":
      return <>{who} created the account <strong>{d}</strong></>;
    case "user_password_reset":
      return <>{who} reset <strong>{d}</strong>&rsquo;s password</>;
    case "user_google_email_set":
      return <>{who} linked a Google email to <strong>{d}</strong></>;
    case "user_google_email_cleared":
      return <>{who} removed the Google email from <strong>{d}</strong></>;
    default:
      return <>{who} {row.action.replace(/_/g, " ")} {d}</>;
  }
}

function alertSentence(row) {
  const who = <strong>{row.actor ?? "Someone"}</strong>;
  const verb = row.action === "alert_acknowledged" ? "acknowledged" : row.action === "alert_resolved" ? "resolved" : row.action.replace("alert_", "");
  const a = row.alert;
  if (!a) return <>{who} {verb} {row.detail}</>;
  return (
    <>
      {who} {verb} a <StatusChip role={severityRole(a.severity)} label={a.severity} /> alert for <strong>{a.catchment}</strong>
    </>
  );
}

function alertMeta(row) {
  const a = row.alert;
  if (!a || !a.flood_day) return null;
  return `Flood day ${formatDay(a.flood_day)} · score ${a.anomaly_score.toFixed(3)}, threshold ${a.threshold_used.toFixed(3)}`;
}

function SignInTable({ rows }) {
  return (
    <table className="admin-table">
      <thead>
        <tr>
          <th>Time</th>
          <th>User</th>
          <th>Event</th>
          <th>Detail</th>
          <th>Address</th>
          <th>Outcome</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const [label, outcome] = SIGN_IN[r.action] ?? [r.action.replace(/_/g, " "), "progress"];
          return (
            <tr key={r.id}>
              <td className="figure activity-time">{formatTime(r.occurred_at)}</td>
              <td className="admin-table-strong">{r.actor ?? "—"}</td>
              <td>{label}</td>
              <td>{r.detail ?? "—"}</td>
              <td className="figure">{r.ip_address ?? "—"}</td>
              <td>
                <StatusChip role={OUTCOME[outcome][1]} label={OUTCOME[outcome][0]} />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function PipelineTable({ rows }) {
  return (
    <table className="admin-table">
      <thead>
        <tr>
          <th>Time</th>
          <th>Catchment</th>
          <th>Reading for</th>
          <th>Why it was rejected</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const p = pipelineParts(r.detail);
          return (
            <tr key={r.id}>
              <td className="figure activity-time">{formatTime(r.occurred_at)}</td>
              <td className="admin-table-strong">{p.catchment}</td>
              <td className="figure">{p.day ? formatDay(p.day) : "—"}</td>
              <td>{p.reason}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Feed({ rows, area }) {
  return (
    <div className="activity-feed">
      {rows.map((r, i) => {
        const heading = dayHeading(r.occurred_at);
        const showHeading = i === 0 || dayHeading(rows[i - 1].occurred_at) !== heading;
        const meta = area === "alerts" ? alertMeta(r) : null;
        return (
          <div key={r.id}>
            {showHeading && <h3 className="activity-day">{heading}</h3>}
            <div className="activity-item">
              <Avatar name={r.actor ?? "?"} size={34} />
              <div className="activity-item-body">
                <p className="activity-item-text">{area === "alerts" ? alertSentence(r) : accountSentence(r)}</p>
                {meta && <p className="activity-item-meta">{meta}</p>}
              </div>
              <span className="activity-item-time figure">{formatClock(r.occurred_at)}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function exportRows(area, rows) {
  if (area === "sign_in") {
    downloadCsv("sign-ins", ["Time", "User", "Event", "Detail", "Address", "Outcome"], rows.map((r) => {
      const [label, outcome] = SIGN_IN[r.action] ?? [r.action, "progress"];
      return [r.occurred_at, r.actor, label, r.detail, r.ip_address, OUTCOME[outcome][0]];
    }));
  } else if (area === "pipeline") {
    downloadCsv("rejected-readings", ["Time", "Catchment", "Reading for", "Reason"], rows.map((r) => {
      const p = pipelineParts(r.detail);
      return [r.occurred_at, p.catchment, p.day, p.reason];
    }));
  } else {
    downloadCsv(area === "alerts" ? "alert-activity" : "account-activity", ["Time", "User", "Event", "Detail"],
      rows.map((r) => [r.occurred_at, r.actor, r.action.replace(/_/g, " "), r.detail]));
  }
}

// Administration's Activity log tab: one area at a time, filtered by period and search
export default function ActivityTab() {
  const [area, setArea] = useState("sign_in");
  const [period, setPeriod] = useState("7d");
  const [outcome, setOutcome] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState(null);

  const layout = AREAS.find((a) => a.id === area).layout;

  // Wait for a pause in typing before searching
  useEffect(() => {
    const timer = setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    get("/api/logs", { category: area, period, q: search, outcome: area === "sign_in" ? outcome : "", limit: PAGE })
      .then((found) => {
        setRows(found);
        setHasMore(found.length === PAGE);
        setError(null);
      })
      .catch((err) => setError(err.message));
  }, [area, period, search, outcome]);

  function changeArea(next) {
    setRows(null);
    setOutcome("");
    setArea(next);
  }

  function loadMore() {
    const before = rows[rows.length - 1].id;
    get("/api/logs", { category: area, period, q: search, outcome: area === "sign_in" ? outcome : "", limit: PAGE, before })
      .then((found) => {
        setRows((current) => [...current, ...found]);
        setHasMore(found.length === PAGE);
      })
      .catch((err) => setError(err.message));
  }

  return (
    <div className="panel activity-panel">
      <div className="activity-areas" role="tablist" aria-label="Activity areas">
        {AREAS.map((a) => (
          <button
            key={a.id}
            type="button"
            role="tab"
            aria-selected={area === a.id}
            className={area === a.id ? "active" : ""}
            onClick={() => changeArea(a.id)}
          >
            {a.label}
          </button>
        ))}
      </div>

      <div className="activity-filters">
        <input
          type="search"
          className="activity-search"
          placeholder={area === "pipeline" ? "Search catchment or reason" : area === "sign_in" ? "Search user, detail or address" : "Search user or detail"}
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          aria-label="Search activity"
        />
        <select value={period} onChange={(e) => { setRows(null); setPeriod(e.target.value); }} aria-label="Period">
          {PERIODS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
        {area === "sign_in" && (
          <select value={outcome} onChange={(e) => { setRows(null); setOutcome(e.target.value); }} aria-label="Outcome">
            <option value="">All outcomes</option>
            <option value="success">Successful</option>
            <option value="failed">Failed</option>
          </select>
        )}
        <button type="button" className="activity-export" onClick={() => exportRows(area, rows)} disabled={!rows?.length}>
          Export CSV
        </button>
      </div>

      {error && <p className="error">{error}</p>}
      {!rows && !error && <p className="activity-loading">Loading...</p>}
      {rows && rows.length === 0 && <EmptyState>{EMPTY[area]}</EmptyState>}

      {rows && rows.length > 0 && (
        <div className="activity-content">
          {layout === "table" ? (
            area === "sign_in" ? <SignInTable rows={rows} /> : <PipelineTable rows={rows} />
          ) : (
            <Feed rows={rows} area={area} />
          )}
        </div>
      )}

      {rows && rows.length > 0 && (
        <div className="activity-footer">
          <span>Showing {rows.length.toLocaleString()} {rows.length === 1 ? "entry" : "entries"}, newest first</span>
          {hasMore && (
            <button type="button" onClick={loadMore}>
              Load more
            </button>
          )}
        </div>
      )}
    </div>
  );
}
