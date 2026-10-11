import "./StatTile.css";

// The dataviz skill's stat-tile contract: a value and a label, figures
// in tabular-nums so a row of tiles lines up, text in ink tokens never
// a series color (an accent bar signals role without recoloring the
// number itself).
export default function StatTile({ label, value, accent }) {
  return (
    <div className="stat-tile" style={accent ? { "--tile-accent": accent } : undefined}>
      <div className="stat-tile-value">{value}</div>
      <div className="stat-tile-label">{label}</div>
    </div>
  );
}
