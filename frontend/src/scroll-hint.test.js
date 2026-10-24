import { beforeEach, describe, expect, it } from "vitest";

import { setUpScrollHint } from "./scroll-hint.js";

// Spec #338 (ticket #344). jsdom lays nothing out, so each box is given its widths, and a stand-in
// ResizeObserver lets a test say "a size changed" (the text grew, the phone turned, a fold opened).
function fakeWindow() {
  const observers = [];
  class ResizeObserver {
    constructor(callback) {
      this.callback = callback;
      observers.push(this);
    }

    observe() {}
  }
  return {
    document,
    ResizeObserver,
    sizesChanged: () => observers.forEach((observer) => observer.callback([])),
  };
}

function setWidths(box, scrollWidth, clientWidth) {
  Object.defineProperty(box, "scrollWidth", { value: scrollWidth, configurable: true });
  Object.defineProperty(box, "clientWidth", { value: clientWidth, configurable: true });
}

const boxes = () => [...document.querySelectorAll(".scroll-box")];
// What a reader sees: the hint's text, only where it is not hidden.
const shownHints = () =>
  [...document.querySelectorAll("p")].filter((p) => !p.hidden).map((p) => p.textContent);

beforeEach(() => {
  document.body.innerHTML = `
    <main>
      <div class="scroll-box"><table></table></div>
      <div class="scroll-box"><table></table></div>
    </main>`;
});

describe("setUpScrollHint", () => {
  it("shows the hint just above a table wider than its box", () => {
    const win = fakeWindow();
    setUpScrollHint(win);
    setWidths(boxes()[0], 500, 300);
    setWidths(boxes()[1], 300, 300);
    win.sizesChanged();
    expect(shownHints()).toEqual(["表格可以左右滑動"]);
    expect(boxes()[0].previousElementSibling.textContent).toBe("表格可以左右滑動");
  });

  it("keeps the hint hidden until a size is known", () => {
    setUpScrollHint(fakeWindow());
    expect(shownHints()).toEqual([]);
  });

  it("hides the hint again once the table fits", () => {
    const win = fakeWindow();
    setUpScrollHint(win);
    boxes().forEach((box) => setWidths(box, 500, 300));
    win.sizesChanged();
    expect(shownHints()).toHaveLength(2);
    boxes().forEach((box) => setWidths(box, 300, 300));
    win.sizesChanged();
    expect(shownHints()).toEqual([]);
  });
});
