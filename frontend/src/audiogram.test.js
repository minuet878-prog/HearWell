import { describe, expect, it } from "vitest";

import { SYMBOLS, levelAt, nearestFrequency, place, pointKey, x, y } from "./audiogram.js";

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
