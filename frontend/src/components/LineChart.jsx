import { useRef, useState } from "react";
import "./LineChart.css";

const WIDTH = 720;
const HEIGHT = 280;
const PADDING = { top: 28, right: 16, bottom: 28, left: 48 };
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

// A bar with rounded top corners and a square base; a plain rectangle when too small for the radius.
function roundedTopBarPath(x, width, yTop, yBottom) {
  const r = Math.max(0, Math.min(3, width / 2, (yBottom - yTop) / 2));
  if (r < 0.75) {
    return `M${x},${yBottom} L${x},${yTop} L${x + width},${yTop} L${x + width},${yBottom} Z`;
  }
  return [
    `M${x},${yBottom}`,
    `L${x},${yTop + r}`,
    `Q${x},${yTop} ${x + r},${yTop}`,
    `L${x + width - r},${yTop}`,
    `Q${x + width},${yTop} ${x + width},${yTop + r}`,
    `L${x + width},${yBottom}`,
    "Z",
  ].join(" ");
}

/**
 * A single-series SVG chart with a crosshair tooltip and a table view.
 * variant="bars" draws daily rainfall totals as separate bars. The peak reading is always marked.
 * forceTable lets a parent show every chart as a table at once.
 */
export default function LineChart({ title, unit, points, variant = "line", forceTable = false }) {
  const [hoverIndex, setHoverIndex] = useState(null);
  const [showTable, setShowTable] = useState(false);
  const svgRef = useRef(null);

  if (points.length === 0) {
    return <p className="chart-empty">No readings for this selection yet.</p>;
  }

  const effectiveShowTable = forceTable || showTable;

  const values = points.map((p) => p.y);
  const minY = Math.min(0, ...values);
  const maxY = Math.max(...values);
  const yRange = maxY - minY || 1;

  const xFor = (index) =>
    points.length === 1 ? PADDING.left : PADDING.left + (index / (points.length - 1)) * PLOT_WIDTH;
  const yFor = (value) => PADDING.top + PLOT_HEIGHT - ((value - minY) / yRange) * PLOT_HEIGHT;
  const baselineY = yFor(minY);

  const linePath = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${xFor(i)},${yFor(p.y)}`)
    .join(" ");
  const areaPath = `${linePath} L${xFor(points.length - 1)},${baselineY} L${xFor(0)},${baselineY} Z`;

  const barWidth = Math.max(1.5, (PLOT_WIDTH / points.length) * 0.55);

  const yTicks = niceTicks(minY, maxY);

  let peakIndex = 0;
  for (let i = 1; i < points.length; i += 1) {
    if (points[i].y > points[peakIndex].y) peakIndex = i;
  }
  const peakPoint = points[peakIndex];

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
        <h3>
          {title}
          {unit && <span className="line-chart-unit"> {unit}</span>}
        </h3>
        <div className="line-chart-header-right">
          <span className="line-chart-peak">Peak {compactNumber(peakPoint.y)}</span>
          {!forceTable && (
            <button type="button" className="table-toggle" onClick={() => setShowTable((v) => !v)}>
              {effectiveShowTable ? "Show chart" : "Show table"}
            </button>
          )}
        </div>
      </div>

      {effectiveShowTable ? (
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

          {variant === "bars" ? (
            <g className="bar-series">
              {points.map((p, i) => (
                <path
                  key={p.x.toISOString()}
                  d={roundedTopBarPath(xFor(i) - barWidth / 2, barWidth, yFor(p.y), baselineY)}
                  className="bar-mark"
                />
              ))}
            </g>
          ) : (
            <>
              <path d={areaPath} className="area-fill" />
              <path d={linePath} className="line-path" fill="none" />
            </>
          )}

          {/* Peak marker: a dashed guide to the axis and the value */}
          <line
            x1={PADDING.left}
            x2={xFor(peakIndex)}
            y1={yFor(peakPoint.y)}
            y2={yFor(peakPoint.y)}
            className="peak-guide"
          />
          <text
            x={xFor(peakIndex)}
            y={Math.max(PADDING.top - 10, yFor(peakPoint.y) - 10)}
            className="peak-label"
            textAnchor="middle"
          >
            {compactNumber(peakPoint.y)}
          </text>

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

      {hovered && !effectiveShowTable && (
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
