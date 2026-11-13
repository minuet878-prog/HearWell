import { expect, it } from "vitest";

import { BLOCKS, backgroundVolume, impulseResponse, loudness, meterBlocks } from "./simulator.js";

const FREQUENCIES = [250, 500, 1000, 2000, 4000, 8000];
// 高頻下降 and 中重度 as the owner approved them on the #485 mockup.
const HIGH_FREQUENCY = [15, 20, 25, 45, 65, 75];
const MODERATELY_SEVERE = [55, 60, 65, 70, 75, 80];
const NORMAL = [0, 0, 0, 0, 0, 0];

// What the filter really does to a tone of frequency f, in dB: its response worked out sample by
// sample, so a filter that turns some band down twice (as the first, chained version did, #487
// review) shows here.
function heard(impulse, frequency, sampleRate) {
  const w = (2 * Math.PI * frequency) / sampleRate;
  let re = 0;
  let im = 0;
  impulse.forEach((sample, n) => {
    re += sample * Math.cos(w * n);
    im -= sample * Math.sin(w * n);
  });
  return 20 * Math.log10(Math.hypot(re, im));
}

const near = (actual, expected) => expect(Math.abs(actual - expected)).toBeLessThanOrEqual(1);

for (const sampleRate of [48000, 44100]) {
  it(`turns each frequency down by the degree's dB HL (${sampleRate} Hz)`, () => {
    for (const thresholds of [HIGH_FREQUENCY, MODERATELY_SEVERE]) {
      const impulse = impulseResponse(FREQUENCIES, thresholds, sampleRate);
      FREQUENCIES.forEach((frequency, i) => near(heard(impulse, frequency, sampleRate), -thresholds[i]));
    }
  });

  it(`follows the audiogram's line between its frequencies (${sampleRate} Hz)`, () => {
    // Halfway (on an octave scale) between 2000 Hz at 45 dB and 4000 Hz at 65 dB, the line is at
    // 55; between 4000 and 8000 at 70; below 250 and above 8000 it stays level.
    const impulse = impulseResponse(FREQUENCIES, HIGH_FREQUENCY, sampleRate);
    near(heard(impulse, 2828, sampleRate), -55);
    near(heard(impulse, 5657, sampleRate), -70);
    near(heard(impulse, 150, sampleRate), -15);
    near(heard(impulse, 10000, sampleRate), -75);
  });

  it(`leaves normal hearing as it is, delayed as much as a degree (${sampleRate} Hz)`, () => {
    const normal = impulseResponse(FREQUENCIES, NORMAL, sampleRate);
    for (const frequency of [100, ...FREQUENCIES, 11000]) near(heard(normal, frequency, sampleRate), 0);
    // Switching 模擬｜正常聽 mid-sentence must not jump in time: both peak at the same sample.
    const peak = (impulse) => impulse.indexOf(Math.max(...impulse.map(Math.abs)));
    const degree = impulseResponse(FREQUENCIES, MODERATELY_SEVERE, sampleRate).map(Math.abs);
    expect(peak(normal)).toBe(degree.indexOf(Math.max(...degree)));
  });
}

it("lights 8 blocks a band for normal hearing and one fewer for every 12.5 dB lost", () => {
  expect(BLOCKS).toBe(8);
  // The #485 mockup's worked example: 85, 80, 75, 55, 35 and 25 left of 100.
  expect(meterBlocks(HIGH_FREQUENCY)).toEqual([7, 6, 6, 4, 3, 2]);
  expect(meterBlocks(MODERATELY_SEVERE)).toEqual([4, 3, 3, 2, 2, 2]);
  expect(meterBlocks(NORMAL)).toEqual([8, 8, 8, 8, 8, 8]);
});

it("never lights fewer than none or more than eight", () => {
  expect(meterBlocks([-10, 0, 100, 120, 50, 95])).toEqual([8, 8, 0, 0, 4, 0]);
});

it("measures loudness as the root mean square of the samples", () => {
  // A square wave of 0.5 and a sine wave of 1 (0.7071 by hand).
  expect(loudness(Float32Array.from([0.5, -0.5, 0.5, -0.5]))).toBeCloseTo(0.5, 6);
  const sine = Float32Array.from({ length: 4800 }, (_, n) => Math.sin((2 * Math.PI * 100 * n) / 48000));
  expect(loudness(sine)).toBeCloseTo(0.7071, 3);
});

it("leaves the silence before and after a sentence out of its loudness", () => {
  // #488 review: counting the quiet ends made the speech sound 0.6-1.1 dB louder than +5 dB over
  // the restaurant. A tenth of a second of speech at 0.1, with as much silence each side.
  const speech = Float32Array.from({ length: 4800 }, (_, n) => (n % 2 ? -0.1 : 0.1));
  const padded = Float32Array.from([...new Float32Array(4800), ...speech, ...new Float32Array(4800)]);
  expect(loudness(padded)).toBeCloseTo(0.1, 6);
});

it("sets the restaurant so the speech is the given dB above it", () => {
  // Worked by hand: speech 0.1, restaurant 0.05; 5 dB below 0.1 is 0.0562, so turn it up 1.1247.
  expect(backgroundVolume(0.1, 0.05, 5)).toBeCloseTo(1.1247, 4);
  // A restaurant already 5 dB under the speech stays as it is.
  expect(backgroundVolume(0.1, 0.1 / 10 ** (5 / 20), 5)).toBeCloseTo(1, 6);
  // 0 dB: as loud as the speech.
  expect(backgroundVolume(0.2, 0.05, 0)).toBeCloseTo(4, 6);
});
