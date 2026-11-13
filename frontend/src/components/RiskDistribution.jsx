import "./RiskDistribution.css";

/**
 * A segmented bar of catchments by risk category, in the reserved status colours.
 * segments is [{ role, label, count }]; total is the whole they are a share of.
 */
export default function RiskDistribution({ segments, total }) {
  if (total === 0) return null;

  return (
    <div className="risk-distribution">
      <div className="risk-distribution-bar" role="presentation">
        {segments
          .filter((segment) => segment.count > 0)
          .map((segment) => (
            <div
              key={segment.role}
              className={`risk-distribution-segment risk-distribution-segment--${segment.role}`}
              style={{ width: `${(segment.count / total) * 100}%` }}
            />
          ))}
      </div>

      <ul className="risk-distribution-legend">
        {segments.map((segment) => (
          <li key={segment.role} className="risk-distribution-legend-item">
            <span
              className={`risk-distribution-dot risk-distribution-dot--${segment.role}`}
              aria-hidden="true"
            />
            <span className="risk-distribution-legend-label">{segment.label}</span>
            <strong className="risk-distribution-legend-count figure">
              {segment.count} ({Math.round((segment.count / total) * 100)}%)
            </strong>
          </li>
        ))}
      </ul>
    </div>
  );
}
