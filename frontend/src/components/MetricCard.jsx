import "./MetricCard.css";

/**
 * Stat card: a headline value, then a segmented bar (segments against segmentsTotal) or a badge,
 * and a one-line description. glyph is a faint decorative icon; tone is "soft" or "deep" fill.
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
  glyph: Glyph,
}) {
  const toneClass = tone ? ` metric-card--${tone}` : "";
  return (
    <div className={`metric-card${toneClass}`}>
      {Glyph && (
        <span className="metric-card-glyph" aria-hidden="true">
          <Glyph />
        </span>
      )}
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
