import { useEffect, useMemo, useState } from "react";
import StatusChip from "../../components/StatusChip";
import { severityRole } from "../../statusRoles";
import { get } from "../../api";

// Look up one day. The calendar shades every day of the month by its score so a
// wet spell is visible at a glance, and picking a day fetches that day in full:
// the score against the flag line, the alert it raised, and the measured inputs
// behind it. This is what lets a date named in the defence be answered directly.
const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function monthKey(year, month) {
  return `${year}-${String(month + 1).padStart(2, "0")}`;
}

function formatDay(iso) {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    timeZone: "UTC",
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

// Four bands rather than a continuous ramp: a flagged day is its own colour,
// and the rest read as low, middling or rising at a glance.
function band(score, threshold) {
  if (score >= threshold) return "flag";
  if (score >= threshold * 0.63) return "high";
  if (score >= threshold * 0.27) return "mid";
  return "low";
}

function Calendar({ month, days, threshold, selected, onPick, onStep }) {
  const [year, monthIndex] = [Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1];
  const byDay = useMemo(() => {
    const map = new Map();
    days.forEach((d) => map.set(d.day, d));
    return map;
  }, [days]);

  const first = new Date(Date.UTC(year, monthIndex, 1));
  const blanks = (first.getUTCDay() + 6) % 7; // weeks start on Monday
  const total = new Date(Date.UTC(year, monthIndex + 1, 0)).getUTCDate();

  return (
    <div className="lstm-cal-wrap">
      <div className="lstm-cal-head">
        <button type="button" className="lstm-cal-step" onClick={() => onStep(-1)} aria-label="Previous month">
          ‹
        </button>
        <strong>
          {MONTHS[monthIndex]} {year}
        </strong>
        <button type="button" className="lstm-cal-step" onClick={() => onStep(1)} aria-label="Next month">
          ›
        </button>
      </div>

      <div className="lstm-cal">
        {DOW.map((d) => (
          <span key={d} className="lstm-cal-dow">
            {d.slice(0, 1)}
          </span>
        ))}
        {Array.from({ length: blanks }, (_, i) => (
          <span key={`blank-${i}`} className="lstm-cal-day lstm-cal-day--out" />
        ))}
        {Array.from({ length: total }, (_, i) => {
          const iso = `${month}-${String(i + 1).padStart(2, "0")}`;
          const row = byDay.get(iso);
          const score = row ? Number(row.anomaly_score) : null;
          const tone = score === null ? "none" : band(score, threshold);
          return (
            <button
              key={iso}
              type="button"
              disabled={!row}
              onClick={() => onPick(iso)}
              title={row ? `Score ${score.toFixed(3)}` : "Not scored"}
              className={`lstm-cal-day lstm-cal-day--${tone}${selected === iso ? " lstm-cal-day--sel" : ""}`}
            >
              {i + 1}
            </button>
          );
        })}
      </div>

      <div className="lstm-cal-key">
        <span>
          <i className="lstm-cal-swatch lstm-cal-day--low" />
          Low score
        </span>
        <span>
          <i className="lstm-cal-swatch lstm-cal-day--high" />
          Rising
        </span>
        <span>
          <i className="lstm-cal-swatch lstm-cal-day--flag" />
          Flagged
        </span>
        <span>
          <i className="lstm-cal-swatch lstm-cal-day--none" />
          Not scored
        </span>
      </div>
    </div>
  );
}

function DayPanel({ day, threshold }) {
  if (!day) {
    return <div className="lstm-day-panel lstm-day-panel--empty">Pick a day on the calendar.</div>;
  }
  const score = Number(day.anomaly_score);
  return (
    <div className="lstm-day-panel">
      <div className="lstm-day-head">
        <div>
          <div className="lstm-day-catchment">{day.catchment}</div>
          <div className="lstm-day-date">{formatDay(day.day)}</div>
        </div>
        {day.is_anomalous ? (
          <span className="lstm-day-chip lstm-day-chip--flag">
            Flagged
            {day.alert_severity ? `, ${day.alert_severity} alert` : ", no alert on record"}
          </span>
        ) : (
          <span className="lstm-day-chip lstm-day-chip--quiet">Below the flag line</span>
        )}
      </div>

      <div className="lstm-day-score figure">{score.toFixed(3)}</div>
      <div className="lstm-meter" role="presentation">
        <span
          className={`lstm-meter-fill${day.is_anomalous ? " lstm-meter-fill--flag" : ""}`}
          style={{ width: `${Math.min(score, 1) * 100}%` }}
        />
        <span className="lstm-meter-line" style={{ left: `${threshold * 100}%` }} />
      </div>
      <div className="lstm-meter-legend">
        <span>0</span>
        <span>flag {Number(day.threshold_used).toFixed(3)}</span>
        <span>1</span>
      </div>

      {day.alert_id && (
        <p className="lstm-day-alert">
          Alert #{day.alert_id} ·{" "}
          <StatusChip role={severityRole(day.alert_severity)} label={day.alert_severity} /> · {day.alert_status}
        </p>
      )}

      <div className="lstm-inputs">
        {day.inputs.map((input) => (
          <div key={input.label}>
            <div className="lstm-inputs-key">{input.label}</div>
            <div className="lstm-inputs-value figure">
              {input.value === null || input.value === undefined
                ? "—"
                : `${Number(input.value).toFixed(2)}${input.unit ? ` ${input.unit}` : ""}`}
            </div>
          </div>
        ))}
      </div>
      <p className="lstm-caveat">
        These are the measured inputs recorded for this day. The model reads them together with the
        thirteen days before it, so the score reflects the whole run-up, not this day alone.
      </p>
    </div>
  );
}

export default function DayLookupTab({ model, catchments }) {
  const [catchment, setCatchment] = useState(catchments[0] ?? "");
  const [month, setMonth] = useState(null);
  const [calendar, setCalendar] = useState(null);
  const [selected, setSelected] = useState(null);
  const [day, setDay] = useState(null);
  const [error, setError] = useState(null);
  const threshold = model.threshold;

  useEffect(() => {
    if (!catchment) return undefined;
    let current = true;
    get("/api/anomalies/calendar", { catchment, month: month ?? "" })
      .then((result) => {
        if (!current) return;
        setCalendar(result);
        if (month === null) setMonth(result.month);
      })
      .catch((err) => current && setError(err.message));
    return () => {
      current = false;
    };
  }, [catchment, month]);

  useEffect(() => {
    if (!selected || !catchment) return undefined;
    let current = true;
    get("/api/anomalies/day", { catchment, date: selected })
      .then((result) => current && setDay(result))
      .catch((err) => current && setError(err.message));
    return () => {
      current = false;
    };
  }, [selected, catchment]);

  // The panel is cleared where the day changes rather than inside the effect
  // that fetches it, so picking a day does not start a second render first.
  function pickDay(iso) {
    setDay(null);
    setSelected(iso);
  }

  function step(direction) {
    const [year, monthIndex] = [Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1 + direction];
    setCalendar(null);
    setMonth(monthKey(year + Math.floor(monthIndex / 12), ((monthIndex % 12) + 12) % 12));
  }

  function jumpTo(date) {
    if (!date) return;
    setCalendar(null);
    setMonth(date.slice(0, 7));
    pickDay(date);
  }

  const range = calendar?.scored_range;

  return (
    <div className="lstm-tab">
      <div className="lstm-querybar">
        <div className="lstm-seg">
          {catchments.map((name) => (
            <button
              key={name}
              type="button"
              className={catchment === name ? "active" : ""}
              onClick={() => {
                setCatchment(name);
                setSelected(null);
                setDay(null);
              }}
            >
              {name}
            </button>
          ))}
        </div>

        <label className="pill-select">
          <span className="pill-select-key">Jump to</span>
          <input
            type="date"
            value={selected ?? ""}
            min={range?.first_day ?? undefined}
            max={range?.last_day ?? undefined}
            onChange={(e) => jumpTo(e.target.value)}
          />
        </label>

        {range && (
          <span className="lstm-querybar-count">
            Scored {range.first_day} to {range.last_day}
          </span>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      <div className="lstm-lookup">
        {month && calendar && (
          <Calendar
            month={calendar.month}
            days={calendar.days}
            threshold={threshold}
            selected={selected}
            onPick={pickDay}
            onStep={step}
          />
        )}
        <DayPanel day={day} threshold={threshold} />
      </div>
    </div>
  );
}
