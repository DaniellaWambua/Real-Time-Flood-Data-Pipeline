import "./RiskDistribution.css";

/**
 * A segmented bar summarising catchments by risk category, in the
 * spirit of Daniella's reference "Risk Distribution" card - but a
 * bar, not that reference's donut: the dataviz skill prefers a bar
 * for part-to-whole comparisons like this one (the project's own
 * severity-breakdown card made the same choice earlier). Colors come
 * straight from the reserved status palette (good/warning/critical),
 * the same roles StatusChip and the risk map use, never repicked
 * here - this is read by the whole app as one consistent legend.
 *
 * `segments` is `[{ role, label, count }]`; `total` is the whole the
 * segments are a share of (catchments.length on the Overview page).
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
