import { SYMBOLS } from "./audiogram.js";

// #617 (spec #611 K1, the #613 mockup's B): a point of the chart in large type, the symbol's name
// small over its frequency and level; until there is a point, where to tap. `point` is shaped as a
// marked one ({ear, conduction, frequency, db, no_response, masked}), or null. The box keeps the
// height of the longest reading whatever it says (site.css), so the chart under it never moves.
// The demo of #618 shows one over its own chart.
const nameOf = (point) => SYMBOLS.find((s) => s.ear === point.ear && s.conduction === point.conduction).label;
const valueOf = (point) =>
  [`${point.frequency} Hz`, point.no_response ? "無反應" : `${point.db} dB`, ...(point.masked ? ["遮蔽"] : [])].join("　");

// The same point in one line, for a status area to say.
export const readingText = (point) => `${nameOf(point)}　${valueOf(point)}`;

export default function AudiogramReading({ point }) {
  return (
    <div className="audiogram-reading">
      {point ? (
        <>
          <span className="audiogram-reading-name">{nameOf(point)}</span>
          <span className="audiogram-reading-value">{valueOf(point)}</span>
        </>
      ) : (
        <span className="audiogram-reading-hint">點一下圖來標記</span>
      )}
    </div>
  );
}
