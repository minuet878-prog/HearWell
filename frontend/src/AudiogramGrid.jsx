import { AIR_FREQUENCIES, CHART, DB_MIN, x, y } from "./audiogram.js";

const freqLabel = (f) => (f >= 1000 ? `${f / 1000}k` : String(f));

// An audiogram's grid with its dB and Hz numbers: a line every 10 dB from -10 down to `downTo`,
// the frequency lines down to `bottom`. `normalBand` is the green normal range down to 25 dB.
// Shared by the user's chart and the smaller marking demo, which stops at 70 dB.
export default function AudiogramGrid({ downTo = 120, bottom = y(downTo), normalBand = true }) {
  const dbs = Array.from({ length: (downTo - DB_MIN) / 10 + 1 }, (_, i) => DB_MIN + i * 10);
  return (
    <>
      {normalBand && <rect x={CHART.left} y={y(DB_MIN)} width={CHART.right - CHART.left} height={y(25) - y(DB_MIN)} fill="#e9f5ec" />}
      {dbs.map((db) => (
        <g key={db}>
          <line x1={CHART.left} x2={CHART.right} y1={y(db)} y2={y(db)} stroke={db === 0 ? "#555" : "#c9d1dc"} strokeWidth={db === 0 ? 1.5 : 1} />
          <text x={CHART.left - 5} y={y(db) + 5} textAnchor="end" fontSize="14" fill="#333">
            {db}
          </text>
        </g>
      ))}
      {AIR_FREQUENCIES.map((f) => (
        <g key={f}>
          <line x1={x(f)} x2={x(f)} y1={CHART.top} y2={bottom} stroke="#c9d1dc" strokeDasharray={f === 3000 || f === 6000 ? "3 3" : undefined} />
          <text x={x(f)} y={CHART.top - 9} textAnchor="middle" fontSize="14" fill="#333">
            {freqLabel(f)}
          </text>
        </g>
      ))}
    </>
  );
}
