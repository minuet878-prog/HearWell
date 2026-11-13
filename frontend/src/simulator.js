// The hearing loss simulator's sums (#487, spec #484, ADR 0052): how far to turn each band down,
// and how many blocks of the sound bars stay lit. thresholds is a typical degree's representative
// audiogram in dB HL at frequencies (screening/simulator.py), or null for 正常聽.

const BLOCKS = 8;
const DB_PER_BLOCK = 100 / BLOCKS;
// About an octave wide, so neighbouring peaks meet.
const OCTAVE_Q = 1.41;

// BiquadFilterNode settings: a shelf at each end, peaks between, each band down by its dB HL.
export function filterBands(frequencies, thresholds) {
  const last = frequencies.length - 1;
  return frequencies.map((frequency, i) => {
    const gain = thresholds ? -thresholds[i] : 0;
    if (i === 0) return { type: "lowshelf", frequency, gain };
    if (i === last) return { type: "highshelf", frequency, gain };
    return { type: "peaking", frequency, gain, Q: OCTAVE_Q };
  });
}

// Lit blocks a band: 8 for normal hearing, one fewer for every 12.5 dB lost (the #485 mockup).
export function meterBlocks(thresholds) {
  if (!thresholds) return Array(6).fill(BLOCKS);
  return thresholds.map((db) => Math.min(BLOCKS, Math.max(0, Math.round((100 - db) / DB_PER_BLOCK))));
}
