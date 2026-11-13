import { expect, it } from "vitest";

import { filterBands, meterBlocks } from "./simulator.js";

const FREQUENCIES = [250, 500, 1000, 2000, 4000, 8000];
// 高頻下降 as the owner approved it on the #485 mockup.
const HIGH_FREQUENCY = [15, 20, 25, 45, 65, 75];

it("turns each band down by the degree's dB HL, a shelf at each end and peaks between", () => {
  expect(filterBands(FREQUENCIES, HIGH_FREQUENCY)).toEqual([
    { type: "lowshelf", frequency: 250, gain: -15 },
    { type: "peaking", frequency: 500, gain: -20, Q: 1.41 },
    { type: "peaking", frequency: 1000, gain: -25, Q: 1.41 },
    { type: "peaking", frequency: 2000, gain: -45, Q: 1.41 },
    { type: "peaking", frequency: 4000, gain: -65, Q: 1.41 },
    { type: "highshelf", frequency: 8000, gain: -75 },
  ]);
});

it("hears normally with the same bands at 0 dB", () => {
  expect(filterBands(FREQUENCIES, null).map((band) => band.gain)).toEqual([0, 0, 0, 0, 0, 0]);
  expect(filterBands(FREQUENCIES, null).map((band) => band.type)).toEqual(
    filterBands(FREQUENCIES, HIGH_FREQUENCY).map((band) => band.type),
  );
});

it("lights 8 blocks a band for normal hearing and one fewer for every 12.5 dB lost", () => {
  // The #485 mockup's worked example: 85, 80, 75, 55, 35 and 25 left of 100.
  expect(meterBlocks(HIGH_FREQUENCY)).toEqual([7, 6, 6, 4, 3, 2]);
  expect(meterBlocks([55, 60, 65, 70, 75, 80])).toEqual([4, 3, 3, 2, 2, 2]);
  expect(meterBlocks(null)).toEqual([8, 8, 8, 8, 8, 8]);
});

it("never lights fewer than none or more than eight", () => {
  expect(meterBlocks([-10, 0, 100, 120, 50, 95])).toEqual([8, 8, 0, 0, 4, 0]);
});
