import { describe, expect, it } from "vitest";

import { isInView } from "./in-view.js";

// Spec #338 (ticket #341): an entrance animation plays once its element is in view: wholly
// inside what is visible above the bottom tab bar, or, for one taller than half of that, filling
// at least half of it. An 800px window with an 80px tab bar leaves 720px to see.
const rect = (top, height) => ({ top, bottom: top + height });

describe("isInView", () => {
  it("is in view wholly inside the visible area", () => {
    expect(isInView(rect(100, 200), 800, 80)).toBe(true);
  });

  it("is not in view while only partly showing at the bottom", () => {
    expect(isInView(rect(600, 200), 800, 80)).toBe(false);
  });

  it("is not in view while partly scrolled off the top", () => {
    expect(isInView(rect(-10, 200), 800, 80)).toBe(false);
  });

  it("is not in view while its foot is under the tab bar", () => {
    expect(isInView(rect(530, 200), 800, 80)).toBe(false);
  });

  it("is in view with its foot just above the tab bar", () => {
    expect(isInView(rect(520, 200), 800, 80)).toBe(true);
  });

  it("is not in view below the screen", () => {
    expect(isInView(rect(900, 200), 800, 80)).toBe(false);
  });

  it("is in view when taller than half the visible area and filling half of it", () => {
    expect(isInView(rect(360, 1000), 800, 80)).toBe(true);
  });

  it("is in view when taller than the visible area and filling all of it", () => {
    expect(isInView(rect(-500, 2000), 800, 80)).toBe(true);
  });

  it("is not in view when taller than half the visible area but filling less than half", () => {
    expect(isInView(rect(361, 1000), 800, 80)).toBe(false);
  });
});
