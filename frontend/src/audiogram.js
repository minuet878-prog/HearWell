// Audiogram input rules (spec docs/specs/phase5_audiogram.md 4.1). The same limits are
// checked again by the API; interpretation is the server's job and never done here.

export const AIR_FREQUENCIES = [250, 500, 1000, 2000, 3000, 4000, 6000, 8000];
export const BONE_FREQUENCIES = [500, 1000, 2000, 4000];
export const DB_MIN = -10;
// A no-response point sits at its conduction's maximum.
export const DB_MAX = { air: 120, bone: 80 };
const STEP = 5;

// ASHA marks: unmasked, then masked.
export const SYMBOLS = [
  { key: "right-air", ear: "right", conduction: "air", label: "右耳氣導", mark: "○", maskedMark: "△" },
  { key: "left-air", ear: "left", conduction: "air", label: "左耳氣導", mark: "✕", maskedMark: "□" },
  { key: "right-bone", ear: "right", conduction: "bone", label: "右耳骨導", mark: "<", maskedMark: "[" },
  { key: "left-bone", ear: "left", conduction: "bone", label: "左耳骨導", mark: ">", maskedMark: "]" },
];

// Chart units; the SVG scales to its box. The space below 120 dB is where a drag becomes "no response".
export const CHART = { width: 320, height: 380, left: 36, right: 304, top: 30, bottom: 342 };

export const frequenciesFor = (conduction) => (conduction === "air" ? AIR_FREQUENCIES : BONE_FREQUENCIES);

// Octaves are evenly spaced, as on a clinical audiogram (250 to 8000 Hz is five octaves).
export const x = (frequency) => CHART.left + (Math.log2(frequency / 250) / 5) * (CHART.right - CHART.left);
// dB HL increases downwards.
export const y = (db) => CHART.top + ((db - DB_MIN) / (120 - DB_MIN)) * (CHART.bottom - CHART.top);

export function nearestFrequency(px, conduction) {
  return frequenciesFor(conduction).reduce((best, f) => (Math.abs(x(f) - px) < Math.abs(x(best) - px) ? f : best));
}

export function levelAt(py, conduction) {
  const raw = DB_MIN + ((py - CHART.top) / (CHART.bottom - CHART.top)) * (120 - DB_MIN);
  const db = Math.max(DB_MIN, Math.round(raw / STEP) * STEP) || 0; // `|| 0` turns -0 into 0
  const max = DB_MAX[conduction];
  return db > max ? { db: max, noResponse: true } : { db, noResponse: false };
}

export const pointKey = (ear, conduction, frequency) => `${ear}-${conduction}-${frequency}`;

// Releasing on the very point (value, no response and masking) deletes it; anything else adds,
// moves or re-marks it, so tapping with the other masking converts the point.
export function place(points, symbol, frequency, level, masked = false) {
  const key = pointKey(symbol.ear, symbol.conduction, frequency);
  const { [key]: existing, ...others } = points;
  if (existing && existing.db === level.db && existing.no_response === level.noResponse && existing.masked === masked) {
    return others;
  }
  const point = { ear: symbol.ear, conduction: symbol.conduction, frequency, db: level.db, no_response: level.noResponse, masked };
  return { ...points, [key]: point };
}
