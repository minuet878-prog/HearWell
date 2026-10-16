import { useRef, useState } from "react";

import { AIR_FREQUENCIES, CHART, DB_MIN, levelAt, nearestFrequency, pointKey, x, y } from "./audiogram.js";

const COLORS = { right: "#c0392b", left: "#1f4e8c" };
const GRID_DBS = Array.from({ length: 14 }, (_, i) => DB_MIN + i * 10);
const freqLabel = (f) => (f >= 1000 ? `${f / 1000}k` : String(f));
// Above this level there is no room over the point, so the magnifier goes beside it.
const MAGNIFIER_ABOVE_FROM = 10;
const percent = (value, total) => `${(value / total) * 100}%`;

function Mark({ point }) {
  const color = COLORS[point.ear];
  const cx = x(point.frequency);
  const cy = y(point.db);
  const isRight = point.ear === "right";
  let mark;
  if (point.conduction === "bone") {
    // Bone marks sit beside the line: <, [ to the left for the right ear; >, ] to the right for the left.
    const bone = point.masked ? (isRight ? "[" : "]") : isRight ? "<" : ">";
    mark = (
      <text x={cx + (isRight ? -11 : 11)} y={cy + 6} textAnchor="middle" fontSize="18" fontWeight="700" fill={color}>
        {bone}
      </text>
    );
  } else if (point.masked && isRight) {
    mark = <polygon points={`${cx},${cy - 7} ${cx - 7},${cy + 5} ${cx + 7},${cy + 5}`} fill="#fff" stroke={color} strokeWidth="2" />;
  } else if (point.masked) {
    mark = <rect x={cx - 6} y={cy - 6} width="12" height="12" fill="#fff" stroke={color} strokeWidth="2" />;
  } else if (isRight) {
    mark = <circle cx={cx} cy={cy} r="6" fill="#fff" stroke={color} strokeWidth="2" />;
  } else {
    mark = (
      <path d={`M${cx - 5} ${cy - 5}L${cx + 5} ${cy + 5}M${cx - 5} ${cy + 5}L${cx + 5} ${cy - 5}`} stroke={color} strokeWidth="2.2" />
    );
  }
  // No response: an arrow pointing down and away from the other ear.
  const dx = isRight ? -1 : 1;
  const bx = cx + (point.conduction === "bone" ? dx * 11 : 0);
  return (
    <g
      data-point={pointKey(point.ear, point.conduction, point.frequency)}
      data-db={point.db}
      data-no-response={point.no_response}
      data-masked={Boolean(point.masked)}
    >
      {mark}
      {point.no_response && (
        <path
          className="no-response-arrow"
          d={`M${bx} ${cy + 7}l${dx * 8} ${12}m${-dx * 5} 0l${dx * 5} 0l0 -5`}
          fill="none"
          stroke={color}
          strokeWidth="2"
        />
      )}
    </g>
  );
}

// Air marks of one ear joined in frequency order; a no-response point breaks the line.
function airLines(points, ear) {
  const pieces = [[]];
  AIR_FREQUENCIES.forEach((f) => {
    const p = points.find((q) => q.ear === ear && q.conduction === "air" && q.frequency === f);
    if (!p) return;
    if (p.no_response) pieces.push([]);
    else pieces[pieces.length - 1].push(p);
  });
  return pieces.filter((piece) => piece.length > 1);
}

// Read-only without `symbol`; with it, press-drag-release reports onCommit(frequency, level).
// `masked` only shapes the point drawn while dragging.
export default function AudiogramChart({ points, symbol, masked = false, onCommit }) {
  const svg = useRef(null);
  const dragging = useRef(null);
  const [preview, setPreview] = useState(null);

  const toChart = (event) => {
    const box = svg.current.getBoundingClientRect();
    return {
      px: ((event.clientX - box.left) * CHART.width) / box.width,
      py: ((event.clientY - box.top) * CHART.height) / box.height,
    };
  };
  const track = (event, frequency) => {
    const next = { frequency, level: levelAt(toChart(event).py, symbol.conduction) };
    dragging.current = next;
    setPreview(next);
    return next;
  };

  const finish = ({ frequency, level }) => {
    dragging.current = null;
    setPreview(null);
    onCommit(frequency, level);
  };

  const handlers = symbol && {
    onPointerDown(event) {
      event.preventDefault();
      svg.current.setPointerCapture?.(event.pointerId);
      // The frequency is fixed on press; dragging only changes the level.
      track(event, nearestFrequency(toChart(event).px, symbol.conduction));
    },
    onPointerMove(event) {
      if (dragging.current) track(event, dragging.current.frequency);
    },
    onPointerUp(event) {
      if (dragging.current) finish(track(event, dragging.current.frequency));
    },
    // Chrome can drop the capture before the release (seen with a Mac trackpad); the release then
    // goes to another element and never reaches onPointerUp, so the drag ends here instead,
    // at the last level shown. In the normal order this runs after onPointerUp and does nothing.
    onLostPointerCapture() {
      if (dragging.current) finish(dragging.current);
    },
    onPointerCancel() {
      dragging.current = null;
      setPreview(null);
    },
  };

  let shown = points;
  if (preview) {
    const key = pointKey(symbol.ear, symbol.conduction, preview.frequency);
    const draft = { ear: symbol.ear, conduction: symbol.conduction, frequency: preview.frequency, db: preview.level.db, no_response: preview.level.noResponse, masked };
    shown = [...points.filter((p) => pointKey(p.ear, p.conduction, p.frequency) !== key), draft];
  }

  return (
    <div className="audiogram-plot">
      <svg
        ref={svg}
        viewBox={`0 0 ${CHART.width} ${CHART.height}`}
        role="img"
        aria-label={symbol ? "聽力圖（用手指按住拖曳標記；鍵盤請用下方的數值表）" : "聽力圖"}
        className="audiogram-svg"
        style={symbol ? { touchAction: "none" } : undefined}
        {...handlers}
      >
        <rect x={CHART.left} y={y(DB_MIN)} width={CHART.right - CHART.left} height={y(25) - y(DB_MIN)} fill="#e9f5ec" />
        {GRID_DBS.map((db) => (
          <g key={db}>
            <line x1={CHART.left} x2={CHART.right} y1={y(db)} y2={y(db)} stroke={db === 0 ? "#555" : "#c9d1dc"} strokeWidth={db === 0 ? 1.5 : 1} />
            <text x={CHART.left - 5} y={y(db) + 5} textAnchor="end" fontSize="14" fill="#333">
              {db}
            </text>
          </g>
        ))}
        {AIR_FREQUENCIES.map((f) => (
          <g key={f}>
            <line x1={x(f)} x2={x(f)} y1={CHART.top} y2={CHART.bottom} stroke="#c9d1dc" strokeDasharray={f === 3000 || f === 6000 ? "3 3" : undefined} />
            <text x={x(f)} y={CHART.top - 9} textAnchor="middle" fontSize="14" fill="#333">
              {freqLabel(f)}
            </text>
          </g>
        ))}
        <rect x={CHART.left} y={CHART.top} width={CHART.right - CHART.left} height={CHART.bottom - CHART.top} fill="none" stroke="#555" />
        {["right", "left"].flatMap((ear) =>
          airLines(shown, ear).map((piece) => (
            <polyline
              key={`${ear}-${piece[0].frequency}`}
              className={`air-line-${ear}`}
              points={piece.map((p) => `${x(p.frequency)},${y(p.db)}`).join(" ")}
              fill="none"
              stroke={COLORS[ear]}
              strokeWidth="1.5"
            />
          )),
        )}
        {shown.map((p) => (
          <Mark key={pointKey(p.ear, p.conduction, p.frequency)} point={p} />
        ))}
      </svg>
      {/* HTML, not SVG text, so it is sized in rem and grows with the user's font size (review 1-2). */}
      {preview && (
        <div
          className="audiogram-magnifier"
          data-place={preview.level.db > MAGNIFIER_ABOVE_FROM ? "above" : "beside"}
          data-side={x(preview.frequency) > (CHART.left + CHART.right) / 2 ? "left" : "right"}
          style={{ left: percent(x(preview.frequency), CHART.width), top: percent(y(preview.level.db), CHART.height) }}
        >
          {`${preview.frequency} Hz ${preview.level.noResponse ? "無反應" : `${preview.level.db} dB`}${masked ? " 遮蔽" : ""}`}
        </div>
      )}
    </div>
  );
}
