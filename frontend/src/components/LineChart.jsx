import { useRef, useState } from "react";
import "./LineChart.css";

const WIDTH = 720;
const HEIGHT = 280;
const PADDING = { top: 16, right: 16, bottom: 28, left: 48 };
const PLOT_WIDTH = WIDTH - PADDING.left - PADDING.right;
const PLOT_HEIGHT = HEIGHT - PADDING.top - PADDING.bottom;

function compactNumber(value) {
  if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function niceTicks(min, max, count = 4) {
  if (min === max) return [min];
  const step = (max - min) / count;
  return Array.from({ length: count + 1 }, (_, i) => min + step * i);
}

/**
 * A single-series line chart in plain SVG (dataviz skill: thin 2px line,
 * end-marker with a surface ring, hairline gridlines, a crosshair tooltip,
 * and a table-view toggle as the accessibility twin). One series only, by
 * design, so no legend box, per that skill's rule that a single series
 * names itself in the title.
 */
export default function LineChart({ title, unit, points }) {
  const [hoverIndex, setHoverIndex] = useState(null);
  const [showTable, setShowTable] = useState(false);
  const svgRef = useRef(null);

  if (points.length === 0) {
    return <p className="chart-empty">No readings for this selection yet.</p>;
  }

  const values = points.map((p) => p.y);
  const minY = Math.min(0, ...values);
  const maxY = Math.max(...values);
  const yRange = maxY - minY || 1;

  const xFor = (index) =>
    points.length === 1 ? PADDING.left : PADDING.left + (index / (points.length - 1)) * PLOT_WIDTH;
  const yFor = (value) => PADDING.top + PLOT_HEIGHT - ((value - minY) / yRange) * PLOT_HEIGHT;

  const linePath = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${xFor(i)},${yFor(p.y)}`)
    .join(" ");

  const yTicks = niceTicks(minY, maxY);

  function handlePointerMove(event) {
    const rect = svgRef.current.getBoundingClientRect();
    const relativeX = ((event.clientX - rect.left) / rect.width) * WIDTH;
    const ratio = Math.min(1, Math.max(0, (relativeX - PADDING.left) / PLOT_WIDTH));
    const index = Math.round(ratio * (points.length - 1));
    setHoverIndex(index);
  }

  const hovered = hoverIndex !== null ? points[hoverIndex] : null;

  return (
    <div className="line-chart">
      <div className="line-chart-header">
        <h3>{title}</h3>
        <button type="button" className="table-toggle" onClick={() => setShowTable((v) => !v)}>
          {showTable ? "Show chart" : "Show table"}
        </button>
      </div>

      {showTable ? (
        <table className="line-chart-table">
          <thead>
            <tr>
              <th>Recorded at</th>
              <th>{unit ? `Value (${unit})` : "Value"}</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.x.toISOString()}>
                <td>{p.x.toLocaleString()}</td>
                <td>{p.y}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <svg
          ref={svgRef}
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="line-chart-svg"
          onPointerMove={handlePointerMove}
          onPointerLeave={() => setHoverIndex(null)}
        >
          {yTicks.map((tick) => (
            <g key={tick}>
              <line
                x1={PADDING.left}
                x2={WIDTH - PADDING.right}
                y1={yFor(tick)}
                y2={yFor(tick)}
                className="gridline"
              />
              <text x={PADDING.left - 8} y={yFor(tick)} className="axis-label" textAnchor="end" dy="0.32em">
                {compactNumber(tick)}
              </text>
            </g>
          ))}

          <path d={linePath} className="line-path" fill="none" />

          {hovered && (
            <>
              <line
                x1={xFor(hoverIndex)}
                x2={xFor(hoverIndex)}
                y1={PADDING.top}
                y2={HEIGHT - PADDING.bottom}
                className="crosshair"
              />
              <circle cx={xFor(hoverIndex)} cy={yFor(hovered.y)} r="4" className="end-marker" />
            </>
          )}

          {/* Always mark the latest point, per "lines -> value at the end". */}
          <circle
            cx={xFor(points.length - 1)}
            cy={yFor(points[points.length - 1].y)}
            r="4"
            className="end-marker"
          />
        </svg>
      )}

      {hovered && !showTable && (
        <div className="line-chart-tooltip" role="status">
          <strong>
            {hovered.y}
            {unit ? ` ${unit}` : ""}
          </strong>
          <span>{hovered.x.toLocaleString()}</span>
        </div>
      )}
    </div>
  );
}
