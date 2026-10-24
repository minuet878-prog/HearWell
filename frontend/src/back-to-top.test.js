import { describe, expect, it } from "vitest";

import { shouldShowBackToTop } from "./back-to-top.js";

// Spec #338 (ticket #340): the button shows once the page has scrolled more than two
// viewport heights, and folds away again within them.
describe("shouldShowBackToTop", () => {
  it("stays hidden at exactly two viewport heights", () => {
    expect(shouldShowBackToTop(1600, 800)).toBe(false);
  });

  it("shows a little past two viewport heights", () => {
    expect(shouldShowBackToTop(1601, 800)).toBe(true);
  });

  it("stays hidden a little short of two viewport heights", () => {
    expect(shouldShowBackToTop(1599, 800)).toBe(false);
  });

  it("stays hidden at the top of the page", () => {
    expect(shouldShowBackToTop(0, 800)).toBe(false);
  });
});
