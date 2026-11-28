import { beforeEach, describe, expect, it } from "vitest";

import { GLOW_KEY, setUpPageGlow } from "./page-glow.js";

// The owner's 2026-11-28 pick (G1): the glow sits under the current tab. jsdom lays nothing out,
// so the page's width and the tab's box are stood in for.
function fakeWindow() {
  const win = new EventTarget();
  Object.assign(win, { document, sessionStorage: window.sessionStorage });
  return win;
}

function pageWidth(width) {
  Object.defineProperty(document.documentElement, "clientWidth", {
    value: width,
    configurable: true,
  });
}

function tabAt(left, width) {
  const tab = document.querySelector('.site-nav a[aria-current="page"]');
  tab.getBoundingClientRect = () => ({ left, width });
}

const glowX = () => document.documentElement.style.getPropertyValue("--glow-x");

beforeEach(() => {
  window.sessionStorage.clear();
  document.documentElement.removeAttribute("style");
  document.body.innerHTML = `
    <div class="page-glow" aria-hidden="true"><div></div></div>
    <nav class="site-nav"><ul>
      <li><a href="/">首頁</a></li>
      <li><a href="/q" aria-current="page">問卷</a></li>
    </ul></nav>`;
  pageWidth(1000);
});

describe("setUpPageGlow", () => {
  it("puts the glow under the current tab's middle", () => {
    tabAt(200, 100);
    setUpPageGlow(fakeWindow());
    expect(glowX()).toBe("25%");
  });

  it("keeps where it is for the next page to slide from", () => {
    tabAt(200, 100);
    setUpPageGlow(fakeWindow());
    expect(window.sessionStorage.getItem(GLOW_KEY)).toBe("25%");
  });

  it("puts it in the middle on a page with no current tab", () => {
    document.querySelector("[aria-current]").removeAttribute("aria-current");
    setUpPageGlow(fakeWindow());
    expect(glowX()).toBe("50%");
  });

  it("puts it in the middle where the tab bar is left out", () => {
    tabAt(0, 0);
    setUpPageGlow(fakeWindow());
    expect(glowX()).toBe("50%");
  });

  it("follows the tab when the page is resized", () => {
    tabAt(200, 100);
    const win = fakeWindow();
    setUpPageGlow(win);
    pageWidth(500);
    win.dispatchEvent(new Event("resize"));
    expect(glowX()).toBe("50%");
  });

  it("still places the glow when the browser keeps nothing", () => {
    tabAt(200, 100);
    const win = fakeWindow();
    win.sessionStorage = {
      setItem() {
        throw new Error("blocked");
      },
    };
    setUpPageGlow(win);
    expect(glowX()).toBe("25%");
  });
});
