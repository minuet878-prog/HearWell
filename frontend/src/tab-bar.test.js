import { beforeEach, describe, expect, it } from "vitest";

import { setUpTabBar } from "./tab-bar.js";

// #457 (ADR 0045). jsdom does not scroll, so a stand-in window holds where the page is and how
// tall it is, and says "the page scrolled" with a scroll event; the bar itself is the real
// layout's nav, in jsdom's document.
function fakeWindow({ reducedMotion = false, pageHeight = 3000 } = {}) {
  const win = new EventTarget();
  Object.assign(win, {
    document,
    scrollY: 0,
    innerHeight: 800,
    matchMedia: (query) => ({
      matches: query === "(prefers-reduced-motion: reduce)" && reducedMotion,
    }),
    scrollTo(y) {
      win.scrollY = y;
      win.dispatchEvent(new Event("scroll"));
    },
  });
  Object.defineProperty(document.documentElement, "scrollHeight", {
    value: pageHeight,
    configurable: true,
  });
  return win;
}

const bar = () => document.querySelector(".site-nav");
const isHidden = () => bar().hasAttribute("data-hidden");

beforeEach(() => {
  document.body.innerHTML = `
    <nav class="site-nav"><ul><li><a href="/">首頁</a></li><li><a href="/learn">了解</a></li></ul></nav>
    <main><a href="#here">一個連結</a></main>`;
});

describe("setUpTabBar", () => {
  it("shows the bar when the page opens", () => {
    setUpTabBar(fakeWindow());
    expect(isHidden()).toBe(false);
  });

  it("hides the bar while scrolling down and brings it back on scrolling up", () => {
    const win = fakeWindow();
    setUpTabBar(win);
    win.scrollTo(300);
    expect(isHidden()).toBe(true);
    win.scrollTo(600);
    expect(isHidden()).toBe(true);
    win.scrollTo(550);
    expect(isHidden()).toBe(false);
  });

  it("keeps the bar at the top of the page, where an iPhone bounces back down from above it", () => {
    const win = fakeWindow();
    setUpTabBar(win);
    win.scrollTo(-40);
    win.scrollTo(0);
    expect(isHidden()).toBe(false);
  });

  it("never hides the bar with reduced motion", () => {
    const win = fakeWindow({ reducedMotion: true });
    setUpTabBar(win);
    win.scrollTo(300);
    win.scrollTo(600);
    expect(isHidden()).toBe(false);
  });

  it("brings the bar back when the keyboard focus moves onto a tab, and keeps it there", () => {
    const win = fakeWindow();
    setUpTabBar(win);
    win.scrollTo(300);
    bar().querySelector("a").focus();
    expect(isHidden()).toBe(false);
    win.scrollTo(600);
    expect(isHidden()).toBe(false);
  });

  it("hides the bar again once the focus has left it and the page scrolls down", () => {
    const win = fakeWindow();
    setUpTabBar(win);
    bar().querySelector("a").focus();
    document.querySelector("main a").focus();
    win.scrollTo(300);
    expect(isHidden()).toBe(true);
  });

  it("shows the bar at the bottom of the page, even scrolling down to it", () => {
    // 3000 tall, 800 showing: the bottom is at 2200.
    const win = fakeWindow();
    setUpTabBar(win);
    win.scrollTo(1000);
    win.scrollTo(2200);
    expect(isHidden()).toBe(false);
  });

  it("shows the bar within a pixel of the bottom, where a zoomed page stops", () => {
    const win = fakeWindow();
    setUpTabBar(win);
    win.scrollTo(1000);
    win.scrollTo(2199.5);
    expect(isHidden()).toBe(false);
  });
});
