import { beforeEach, describe, expect, it, vi } from "vitest";

import { setUpSiteHeader } from "./site-header.js";

// #748 (spec #741 acceptance 38, 39, story 51; ADR 0079). jsdom neither scrolls nor leaves the
// page, so a stand-in window holds where the page is, its history and where it came from.
function fakeWindow({ canGoBack, historyLength = 1, referrer = "" } = {}) {
  const win = new EventTarget();
  Object.assign(win, {
    document,
    scrollY: 0,
    history: { length: historyLength, back: vi.fn() },
    // undefined: a browser without the Navigation API.
    navigation: canGoBack === undefined ? undefined : { canGoBack },
    location: { origin: "https://tingpal.tw" },
    scrollTo(y) {
      win.scrollY = y;
      win.dispatchEvent(new Event("scroll"));
    },
  });
  Object.defineProperty(document, "referrer", { value: referrer, configurable: true });
  return win;
}

const header = () => document.querySelector(".site-header");
const back = () => document.querySelector("[data-site-back]");
const isScrolled = () => header().hasAttribute("data-scrolled");

// A click the way the browser sends it, so a test can see whether the link was followed.
function press() {
  const event = new MouseEvent("click", { bubbles: true, cancelable: true });
  back().dispatchEvent(event);
  return event;
}

beforeEach(() => {
  document.body.innerHTML = `
    <header class="site-header">
      <p class="site-brand"><a href="/">聽伴</a></p>
      <a class="site-back" href="/" aria-label="回首頁" data-site-back></a>
    </header>
    <main></main>`;
  Object.defineProperty(header(), "offsetHeight", { value: 72, configurable: true });
});

describe("scrolling past the header", () => {
  it("swaps the name for the back button, and back at the top swaps them again", () => {
    const win = fakeWindow();
    setUpSiteHeader(win);
    expect(isScrolled()).toBe(false);
    win.scrollTo(40);
    expect(isScrolled()).toBe(false);
    win.scrollTo(200);
    expect(isScrolled()).toBe(true);
    win.scrollTo(0);
    expect(isScrolled()).toBe(false);
  });

  it("starts swapped on a page opened partway down (back from the next page)", () => {
    const win = fakeWindow();
    win.scrollY = 500;
    setUpSiteHeader(win);
    expect(isScrolled()).toBe(true);
  });
});

describe("the back button", () => {
  it.each([
    ["the Navigation API", { canGoBack: true, historyLength: 1 }],
    [
      "history and a page of this site before it",
      { historyLength: 2, referrer: "https://tingpal.tw/learn" },
    ],
  ])("goes to the previous page of this site, judged by %s", (_, options) => {
    const win = fakeWindow(options);
    setUpSiteHeader(win);
    expect(back().getAttribute("aria-label")).toBe("回上一頁");
    const event = press();
    expect(win.history.back).toHaveBeenCalledOnce();
    expect(event.defaultPrevented).toBe(true);
  });

  // Opened from LINE or typed in: the link's own way home is followed.
  it.each([
    ["the Navigation API", { canGoBack: false, historyLength: 3 }],
    ["history alone", { historyLength: 1 }],
    ["a page of another site before it", { historyLength: 2, referrer: "https://line.me/" }],
    ["no page named before it", { historyLength: 2 }],
  ])("goes home when nothing of this site is before it, judged by %s", (_, options) => {
    const win = fakeWindow(options);
    setUpSiteHeader(win);
    expect(back().getAttribute("aria-label")).toBe("回首頁");
    const event = press();
    expect(win.history.back).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });
});
