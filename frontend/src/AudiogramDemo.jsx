import { useEffect, useState } from "react";

import AudiogramGrid from "./AudiogramGrid.jsx";
import AudiogramReading from "./AudiogramReading.jsx";
import { CHART, x, y } from "./audiogram.js";

// #618 (spec #611 K2, the #613 mockup's part five; ADR 0060's three rules): under 怎麼標記, a small
// chart of its own where 看示範 plays a finger tapping 1000 Hz 45 dB, the step's ear's symbol
// coming up and the reading over it saying the point. Played once on a tap, about 2 seconds, then
// it stays on the last frame; ↺ 再看一次 plays it from the start. Never on the user's chart, and
// with reduced motion it is not there at all: the three steps in words say it all.

const POINT = { conduction: "air", frequency: 1000, db: 45, no_response: false, masked: false };
const [PX, PY] = [x(POINT.frequency), y(POINT.db)];
// Only the top of an audiogram, down to 70 dB.
const BOTTOM = y(70) + 10;

// The mockup's table of moves, in ms. The finger is [right, down, clockwise degrees] of its tip.
const DURATION = 2000;
const TAP = 1100;
const RING_GONE = 1400;
const CORNER_START = [273, 218, 30];
const ON_THE_POINT = [PX + 8, PY + 7, 38];
const CORNER_END = [261, 212, 30];
const FINGER = [
  [300, CORNER_START],
  [TAP, ON_THE_POINT],
  [RING_GONE, ON_THE_POINT],
  [DURATION, CORNER_END],
];

// Slow out of one place and slow into the next, as wear-motion.js eases.
const ease = (t) => (t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2);
const round = (n) => Math.round(n * 100) / 100;

function fingerAt(ms) {
  if (ms <= FINGER[0][0]) return FINGER[0][1];
  for (let i = 1; i < FINGER.length; i++) {
    const [[fromMs, from], [toMs, to]] = [FINGER[i - 1], FINGER[i]];
    if (ms < toMs) {
      const t = ease((ms - fromMs) / (toMs - fromMs));
      return from.map((n, j) => n + (to[j] - n) * t);
    }
  }
  return FINGER.at(-1)[1];
}

function Mark({ ear }) {
  const className = `audiogram-demo-mark ear-${ear}`;
  if (ear === "right") return <circle className={className} cx={PX} cy={PY} r="6" />;
  return <path className={className} d={`M${PX - 5} ${PY - 5}L${PX + 5} ${PY + 5}M${PX - 5} ${PY + 5}L${PX + 5} ${PY - 5}`} />;
}

export default function AudiogramDemo({ ear }) {
  const [reducedMotion] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  // Each tap on the button adds a play; the last one runs, from the start.
  const [plays, setPlays] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [played, setPlayed] = useState(false);

  useEffect(() => {
    if (plays === 0) return undefined;
    const start = performance.now();
    let frame;
    const tick = () => {
      const ms = Math.min(performance.now() - start, DURATION);
      setElapsed(ms);
      if (ms < DURATION) frame = requestAnimationFrame(tick);
      else setPlayed(true);
    };
    tick();
    return () => cancelAnimationFrame(frame);
  }, [plays]);

  if (reducedMotion) return null;

  const [fx, fy, turn] = fingerAt(elapsed);
  const tapped = elapsed >= TAP;
  const ring = tapped && elapsed < RING_GONE ? 1 - (elapsed - TAP) / (RING_GONE - TAP) : 0;

  return (
    <>
      <div className="audiogram-demo" aria-hidden="true">
        <AudiogramReading point={tapped ? { ...POINT, ear } : null} />
        <div className="audiogram-demo-chart">
          <svg viewBox={`0 0 ${CHART.width} ${BOTTOM}`} focusable="false">
            <AudiogramGrid downTo={70} bottom={BOTTOM} />
            <rect x={CHART.left} y={CHART.top} width={CHART.right - CHART.left} height={CHART.bottom - CHART.top} fill="none" stroke="#555" />
            {tapped && <Mark ear={ear} />}
            {ring > 0 && <circle className="audiogram-demo-ring" cx={PX + 3} cy={PY + 3} r="14" opacity={round(ring)} />}
            {/* The mockup's fingertip, its tip at the origin, nail and knuckle line drawn in. */}
            <g className="audiogram-demo-finger" transform={`translate(${round(fx)} ${round(fy)}) rotate(${round(turn)}) scale(1.05)`}>
              <path d="M300 -14C180 -12 60 -10 10 -10C0 -10 -4 -4 -4 1C-4 7 1 11 10 11C60 11 180 14 300 18Z" />
              <path className="audiogram-demo-nail" d="M3 -9C9 -11 17 -10 19 -6C20 -3 16 -1 10 -1C5 -1 2 -4 3 -9Z" />
              <path className="audiogram-demo-knuckle" d="M42 -10C44 -5 44 1 42 6" />
            </g>
          </svg>
        </div>
      </div>
      {/* An outline button: the page has a solid 下一步 already. */}
      <button
        type="button"
        className="btn btn-outline-primary audiogram-demo-play"
        onClick={() => setPlays(plays + 1)}
      >
        <span aria-hidden="true">{played ? "↺" : "▶"}</span> {played ? "再看一次" : "看示範"}
      </button>
    </>
  );
}
