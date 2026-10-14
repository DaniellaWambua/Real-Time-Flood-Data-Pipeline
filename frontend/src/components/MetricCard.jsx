import "./MetricCard.css";

/**
 * A richer stat card than StatTile: a big headline value (with an
 * optional muted suffix, e.g. "6 of 6"), then either a segmented
 * progress bar (proportions of a whole, e.g. severity counts) or a
 * status badge when there's nothing to show a proportion of (the
 * Overview screen's LSTM card, which has no live scoring yet), and a
 * one-line description underneath.
 *
 * `segments` is `[{ amount, color }]` plotted against `segmentsTotal`;
 * leftover width (segments summing to less than the total) shows the
 * track's own neutral background, same as an unfilled progress bar.
 * `badge` is `{ role, glyph, label }` and takes the bar's place when
 * there's no meaningful proportion to show.
 *
 * `tone` is the optional filled-card treatment from Daniella's
 * palette spec - "soft" (Pale Ice Blue fill, plain dark text) or
 * "deep" (Forest Green fill, white text), alternated across the
 * Overview screen's four hero cards to match the reference's
 * checkerboard of pale-blue/forest-green cards. Left unset, a card
 * stays the plain white panel it always was (used for Admin's
 * smaller database-overview tiles, which aren't "hero" cards in the
 * same sense).
 */
export default function MetricCard({
  label,
  value,
  valueSuffix,
  segments,
  segmentsTotal,
  badge,
  description,
  tone,
}) {
  const toneClass = tone ? ` metric-card--${tone}` : "";
  return (
    <div className={`metric-card${toneClass}`}>
      <div className="metric-card-label">{label}</div>
      <div className="metric-card-value">
        {value}
        {valueSuffix && <span className="metric-card-suffix">{valueSuffix}</span>}
      </div>

      {badge ? (
        <span className={`metric-card-badge metric-card-badge--${badge.role ?? "muted"}`}>
          {badge.glyph && (
            <span aria-hidden="true" className="metric-card-badge-glyph">
              {badge.glyph}
            </span>
          )}
          {badge.label}
        </span>
      ) : (
        segments &&
        segmentsTotal > 0 && (
          <div className="metric-card-bar" role="presentation">
            {segments.map((segment, index) => (
              <div
                key={index}
                className="metric-card-bar-segment"
                style={{
                  width: `${(segment.amount / segmentsTotal) * 100}%`,
                  background: segment.color,
                }}
              />
            ))}
          </div>
        )
      )}

      {description && <p className="metric-card-description">{description}</p>}
    </div>
  );
}
