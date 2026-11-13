// The hearing loss simulator's sums (#487, spec #484, ADR 0052): the filter that turns a sentence
// down the way a typical degree hears it, and how many blocks of the sound bars stay lit.
// thresholds is a representative audiogram in dB HL at frequencies (screening/simulator.py); 正常聽
// is all zeros.

export const BLOCKS = 8;
const DB_PER_BLOCK = 100 / BLOCKS;
// Taps of the filter: odd, so it has a middle sample to centre on. About 21 ms at 48 kHz.
const TAPS = 1023;

// How far the audiogram's line lies below normal at frequency, in dB: straight between its
// points on an octave scale, as an audiogram is read, and level beyond its ends.
function lineAt(frequencies, thresholds, frequency) {
  const last = frequencies.length - 1;
  if (frequency <= frequencies[0]) return thresholds[0];
  if (frequency >= frequencies[last]) return thresholds[last];
  const i = frequencies.findIndex((f, j) => frequency <= frequencies[j + 1]);
  const along = Math.log2(frequency / frequencies[i]) / Math.log2(frequencies[i + 1] / frequencies[i]);
  return thresholds[i] + (thresholds[i + 1] - thresholds[i]) * along;
}

// A filter (for a ConvolverNode) that turns every frequency down by the audiogram's line, sampled
// along it and windowed (Blackman). One filter for the whole curve: a chain of one filter a band
// turned the bands between twice as far down (#487 review). Its delay is the same for every
// degree and for 正常聽, so switching mid-sentence keeps time.
export function impulseResponse(frequencies, thresholds, sampleRate) {
  const middle = (TAPS - 1) / 2;
  const gains = Array.from({ length: middle + 1 }, (_, k) =>
    10 ** (-lineAt(frequencies, thresholds, (k * sampleRate) / TAPS) / 20),
  );
  return Array.from({ length: TAPS }, (_, n) => {
    let sum = gains[0];
    for (let k = 1; k <= middle; k += 1) sum += 2 * gains[k] * Math.cos((2 * Math.PI * k * (n - middle)) / TAPS);
    const window =
      0.42 - 0.5 * Math.cos((2 * Math.PI * n) / (TAPS - 1)) + 0.08 * Math.cos((4 * Math.PI * n) / (TAPS - 1));
    return (sum / TAPS) * window;
  });
}

// Lit blocks a band: 8 for normal hearing, one fewer for every 12.5 dB lost (the #485 mockup).
export function meterBlocks(thresholds) {
  return thresholds.map((db) => Math.min(BLOCKS, Math.max(0, Math.round((100 - db) / DB_PER_BLOCK))));
}
