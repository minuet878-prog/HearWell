import { useEffect, useRef, useState } from "react";

import { AIR_FREQUENCIES, CHART, DB_MIN, levelAt, nearestFrequency, pointKey, x, y } from "./audiogram.js";

const COLORS = { right: "#c0392b", left: "#1f4e8c" };
// The older audiogram on the compare page: the same ear's colour, lighter (spec phase5_audiogram_2.md 4.2).
const OLD_COLORS = { right: "#e8a59d", left: "#9db5d6" };
const GRID_DBS = Array.from({ length: 14 }, (_, i) => DB_MIN + i * 10);
const freqLabel = (f) => (f >= 1000 ? `${f / 1000}k` : String(f));
// Above this level there is no room over the point, so the magnifier goes beside it.
const MAGNIFIER_ABOVE_FROM = 10;
const percent = (value, total) => `${(value / total) * 100}%`;
// #353: a finger marks only after resting this long, so a swipe that starts on the chart scrolls
// the page; moving further than HOLD_SLOP pixels first is a swipe. dnd-kit's touch default is 250 ms, 5 px.
const HOLD_MS = 300;
const HOLD_SLOP = 10;

function Mark({ point, colors = COLORS }) {
  const color = colors[point.ear];
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

// One audiogram's lines and marks; the older one of a comparison is light and dashed.
function Layer({ points, old = false }) {
  const colors = old ? OLD_COLORS : COLORS;
  return (
    <g className={old ? "audiogram-old" : "audiogram-new"}>
      {["right", "left"].flatMap((ear) =>
        airLines(points, ear).map((piece) => (
          <polyline
            key={`${ear}-${piece[0].frequency}`}
            className={`air-line-${ear}`}
            points={piece.map((p) => `${x(p.frequency)},${y(p.db)}`).join(" ")}
            fill="none"
            stroke={colors[ear]}
            strokeWidth="1.5"
            strokeDasharray={old ? "6 4" : undefined}
          />
        )),
      )}
      {points.map((p) => (
        <Mark key={pointKey(p.ear, p.conduction, p.frequency)} point={p} colors={colors} />
      ))}
    </g>
  );
}

// Read-only without `symbol`; with it, press-drag-release reports onCommit(frequency, level).
// `masked` only shapes the point drawn while dragging. `oldPoints` (read-only) is drawn underneath.
export default function AudiogramChart({ points, oldPoints, symbol, masked = false, onCommit }) {
  const svg = useRef(null);
  const dragging = useRef(null);
  // A finger resting before the drag starts: where it is now, and the timer that starts the drag there.
  const holding = useRef(null);
  const [preview, setPreview] = useState(null);
  const marking = Boolean(symbol);

  // Once a drag has started the page must not scroll under the finger. React listens to touchmove
  // passively, where preventDefault does nothing, so this listener is added by hand.
  useEffect(() => {
    if (!marking) return undefined;
    const chart = svg.current;
    const stopScroll = (event) => {
      if (dragging.current) event.preventDefault();
    };
    chart.addEventListener("touchmove", stopScroll, { passive: false });
    return () => {
      chart.removeEventListener("touchmove", stopScroll);
      clearTimeout(holding.current?.timer);
    };
  }, [marking]);

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

  // The frequency is fixed on press; dragging only changes the level.
  const start = (event) => track(event, nearestFrequency(toChart(event).px, symbol.conduction));
  const stopHolding = () => {
    clearTimeout(holding.current?.timer);
    holding.current = null;
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
      if (event.pointerType !== "touch") {
        start(event);
        return;
      }
      // A second finger means zooming, not marking.
      if (holding.current) {
        stopHolding();
        return;
      }
      const at = { clientX: event.clientX, clientY: event.clientY };
      holding.current = {
        from: at,
        at,
        timer: setTimeout(() => {
          const { at: rested } = holding.current;
          holding.current = null;
          start(rested);
        }, HOLD_MS),
      };
    },
    onPointerMove(event) {
      if (holding.current) {
        const { from } = holding.current;
        if (Math.hypot(event.clientX - from.clientX, event.clientY - from.clientY) > HOLD_SLOP) stopHolding();
        else holding.current.at = { clientX: event.clientX, clientY: event.clientY };
      } else if (dragging.current) {
        track(event, dragging.current.frequency);
      }
    },
    // Letting go before the drag starts is a tap: it marks nothing.
    onPointerUp(event) {
      stopHolding();
      if (dragging.current) finish(track(event, dragging.current.frequency));
    },
    // Chrome can drop the capture before the release (seen with a Mac trackpad); the release then
    // goes to another element and never reaches onPointerUp, so the drag ends here instead,
    // at the last level shown. In the normal order this runs after onPointerUp and does nothing.
    onLostPointerCapture() {
      stopHolding();
      if (dragging.current) finish(dragging.current);
    },
    // Also sent when the browser takes the touch for scrolling.
    onPointerCancel() {
      stopHolding();
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
        aria-label={symbol ? "聽力圖（用手指按住不動一下再拖曳標記；鍵盤請用下方的數值表）" : "聽力圖"}
        className="audiogram-svg"
        style={symbol ? { touchAction: "manipulation" } : undefined}
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
        {oldPoints && <Layer points={oldPoints} old />}
        <Layer points={shown} />
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
