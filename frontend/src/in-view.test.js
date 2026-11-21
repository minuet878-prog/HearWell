import { describe, expect, it } from "vitest";

import { isInView, setUpPlayInView } from "./in-view.js";

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

// Spec #741 (ticket #747, ADR 0077): the play-once mechanism. jsdom neither lays out nor paints,
// so a stand-in window says where each marked element is on screen, says "the page scrolled"
// with a scroll event, and runs animation frames only when the test steps its clock.
function fakeWindow({ reducedMotion = false } = {}) {
  const win = new EventTarget();
  let frames = [];
  Object.assign(win, {
    document,
    innerHeight: 800,
    getComputedStyle: (element) => window.getComputedStyle(element),
    matchMedia: (query) => ({
      matches: query === "(prefers-reduced-motion: reduce)" && reducedMotion,
    }),
    clearTimeout() {},
    ResizeObserver: class {
      observe() {}
      disconnect() {}
    },
    requestAnimationFrame(callback) {
      frames.push(callback);
    },
    // Runs the frames asked for so far at this time (in milliseconds).
    frameAt(time) {
      const due = frames;
      frames = [];
      for (const callback of due) callback(time);
    },
    // Moves an element to this top on screen, then says the page scrolled.
    scrollElementTo(element, top) {
      element.getBoundingClientRect = () => ({ top, bottom: top + 60 });
      win.dispatchEvent(new Event("scroll"));
    },
  });
  return win;
}

// Every marked element starts in view, 100px down a 800px window.
const page = (body) => {
  document.body.innerHTML = `<nav class="site-nav"></nav><main>${body}</main>`;
  for (const element of document.querySelectorAll("[data-play-in-view], [data-count-up]")) {
    element.getBoundingClientRect = () => ({ top: 100, bottom: 160 });
  }
};

const number = () => document.querySelector("[data-count-up]");
const shown = () => number().getAttribute("data-count-now");

describe("setUpPlayInView: numbers that count up", () => {
  it("counts up from 0 to the number once in view, the text staying the number all along", () => {
    page(`<p>總分 <span data-count-up>20</span> 分</p>`);
    const win = fakeWindow();
    setUpPlayInView(win);
    win.frameAt(1000);
    expect(shown()).toBe("0");
    win.frameAt(1450);
    expect(Number(shown())).toBeGreaterThan(0);
    expect(Number(shown())).toBeLessThan(20);
    expect(number().textContent).toBe("20");
    win.frameAt(1900);
    expect(shown()).toBe(null);
    expect(number().hasAttribute("data-count-done")).toBe(true);
    expect(number().textContent).toBe("20");
  });

  it("waits below the screen until scrolled into view, and does not count again", () => {
    page(`<p>總分 <span data-count-up>20</span> 分</p>`);
    const win = fakeWindow();
    win.scrollElementTo(number(), 1200);
    setUpPlayInView(win);
    win.frameAt(1000);
    expect(shown()).toBe(null);
    expect(number().hasAttribute("data-count-done")).toBe(false);

    win.scrollElementTo(number(), 300);
    win.frameAt(2000);
    expect(shown()).toBe("0");
    win.frameAt(2900);
    expect(number().hasAttribute("data-count-done")).toBe(true);

    win.scrollElementTo(number(), 1200);
    win.scrollElementTo(number(), 300);
    win.frameAt(3000);
    expect(shown()).toBe(null);
    expect(number().hasAttribute("data-count-done")).toBe(true);
  });

  it("shows the number at once, without counting, with reduced motion", () => {
    page(`<p>還有 <span data-count-up>45</span> 天</p>`);
    const win = fakeWindow({ reducedMotion: true });
    setUpPlayInView(win);
    expect(number().hasAttribute("data-count-done")).toBe(true);
    win.frameAt(1000);
    expect(shown()).toBe(null);
    expect(number().textContent).toBe("45");
  });
});

describe("setUpPlayInView: entrance animations", () => {
  it("starts an animation once in view and keeps it started after scrolling away and back", () => {
    page(`<div class="play-once-slide-up" data-play-in-view>上次結果</div>`);
    const box = document.querySelector("[data-play-in-view]");
    const win = fakeWindow();
    win.scrollElementTo(box, 1200);
    setUpPlayInView(win);
    expect(box.hasAttribute("data-in-view")).toBe(false);

    win.scrollElementTo(box, 300);
    expect(box.hasAttribute("data-in-view")).toBe(true);
    win.scrollElementTo(box, 1200);
    win.scrollElementTo(box, -900);
    expect(box.hasAttribute("data-in-view")).toBe(true);
  });
});
