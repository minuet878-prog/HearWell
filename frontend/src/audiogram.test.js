import { describe, expect, it } from "vitest";

import { SYMBOLS, levelAt, missedAir, nearestFrequency, place, pointKey, x, y } from "./audiogram.js";

const [rightAir, , , leftBone] = SYMBOLS;

describe("nearestFrequency", () => {
  it("snaps to the closest frequency the conduction allows", () => {
    expect(nearestFrequency(x(1000) + 3, "air")).toBe(1000);
    expect(nearestFrequency(x(3000), "air")).toBe(3000);
    // Bone has no 250, 3000, 6000 or 8000 (spec acceptance 8).
    expect(nearestFrequency(x(3000), "bone")).toBe(4000);
    expect(nearestFrequency(x(6000), "bone")).toBe(4000);
    expect(nearestFrequency(x(8000), "bone")).toBe(4000);
    expect(nearestFrequency(x(250), "bone")).toBe(500);
  });
});

describe("levelAt", () => {
  it("snaps to 5 dB", () => {
    expect(levelAt(y(42), "air")).toEqual({ db: 40, noResponse: false });
    expect(levelAt(y(0), "air")).toEqual({ db: 0, noResponse: false });
  });

  it("stops at -10 above the chart", () => {
    expect(levelAt(y(-40), "air")).toEqual({ db: -10, noResponse: false });
  });

  it("past the bottom is no response at the conduction's maximum", () => {
    expect(levelAt(y(120), "air")).toEqual({ db: 120, noResponse: false });
    expect(levelAt(y(130), "air")).toEqual({ db: 120, noResponse: true });
    expect(levelAt(y(80), "bone")).toEqual({ db: 80, noResponse: false });
    expect(levelAt(y(90), "bone")).toEqual({ db: 80, noResponse: true });
  });
});

describe("place", () => {
  const level = { db: 40, noResponse: false };

  it("adds, moves, and deletes when released on the same point", () => {
    const key = pointKey("right", "air", 1000);
    const added = place({}, rightAir, 1000, level);
    expect(added[key]).toEqual({ ear: "right", conduction: "air", frequency: 1000, db: 40, no_response: false, masked: false });

    const moved = place(added, rightAir, 1000, { db: 60, noResponse: false });
    expect(Object.keys(moved)).toEqual([key]);
    expect(moved[key].db).toBe(60);

    expect(place(moved, rightAir, 1000, { db: 60, noResponse: false })).toEqual({});
  });

  it("a no-response point is a different value from a plain one at the same level", () => {
    const plain = place({}, leftBone, 1000, { db: 80, noResponse: false });
    const nr = place(plain, leftBone, 1000, { db: 80, noResponse: true });
    expect(nr[pointKey("left", "bone", 1000)].no_response).toBe(true);
  });

  it("the same value with other masking converts the point instead of deleting it", () => {
    const key = pointKey("right", "air", 1000);
    const plain = place({}, rightAir, 1000, level);
    const masked = place(plain, rightAir, 1000, level, true);
    expect(masked[key].masked).toBe(true);
    expect(place(masked, rightAir, 1000, level, true)).toEqual({});
  });

  it("leaves the input untouched", () => {
    const before = {};
    place(before, rightAir, 1000, level);
    expect(before).toEqual({});
  });
});

// #619 (spec #611 R1): which air frequencies one ear has and the other has not.
describe("missedAir", () => {
  const mark = (ear, conduction, frequency, extra = {}) => ({
    ear,
    conduction,
    frequency,
    db: 40,
    no_response: false,
    masked: false,
    ...extra,
  });
  const air = (ear, frequencies) => frequencies.map((f) => mark(ear, "air", f));
  const SIX = [250, 500, 1000, 2000, 4000, 8000];

  it("lists what the left ear is missing, low to high (acceptance 50)", () => {
    // Marked out of order: the list still goes from low to high.
    const points = [...air("right", [8000, 2000, 250, 4000, 1000, 500]), ...air("left", [1000, 250, 500])];
    expect(missedAir(points)).toEqual([{ ear: "left", frequencies: [2000, 4000, 8000] }]);
  });

  it("says so for one frequency too (acceptance 51)", () => {
    const points = [...air("right", SIX), ...air("left", [250, 500, 1000, 2000, 4000])];
    expect(missedAir(points)).toEqual([{ ear: "left", frequencies: [8000] }]);
  });

  it("each ear missing different frequencies is one entry each, right first (acceptance 52)", () => {
    const points = [...air("right", [250, 500, 1000, 2000, 4000, 6000]), ...air("left", [250, 500, 1000, 8000])];
    expect(missedAir(points)).toEqual([
      { ear: "right", frequencies: [8000] },
      { ear: "left", frequencies: [2000, 4000, 6000] },
    ]);
  });

  it("nothing when both ears have the same air frequencies (acceptance 53)", () => {
    expect(missedAir([...air("right", SIX), ...air("left", SIX)])).toEqual([]);
    expect(missedAir([])).toEqual([]);
  });

  it("an ear with no air points is not listed, even with bone points (acceptance 54)", () => {
    expect(missedAir(air("right", SIX))).toEqual([]);
    const boneOnly = [...air("right", SIX), mark("left", "bone", 1000), mark("left", "bone", 2000)];
    expect(missedAir(boneOnly)).toEqual([]);
  });

  it("bone is never compared (acceptance 55)", () => {
    const points = [
      ...air("right", SIX),
      ...air("left", SIX),
      mark("right", "bone", 500),
      mark("right", "bone", 1000),
      mark("left", "bone", 4000),
    ];
    expect(missedAir(points)).toEqual([]);
  });

  it("no-response and masked points count as marked (acceptance 56)", () => {
    const points = [
      ...air("right", [250, 500, 1000]),
      mark("left", "air", 250),
      mark("left", "air", 500, { db: 120, no_response: true }),
      mark("left", "air", 1000, { masked: true }),
    ];
    expect(missedAir(points)).toEqual([]);
  });
});
