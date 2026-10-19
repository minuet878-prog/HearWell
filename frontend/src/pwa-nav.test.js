import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PULL_THRESHOLD, setUpPwaNav } from "./pwa-nav.js";

// Spec docs/specs/phase-10/phase10_pwa_back_refresh.md. A stand-in window so tests can see
// back(), assign() and reload() calls, which jsdom cannot perform.
function fakeWindow({
  iphone = true,
  android = false,
  historyLength = 2,
  canGoBack, // undefined: a browser without the Navigation API
  scale = 1,
  scrollY = 0,
} = {}) {
  return Object.assign(new EventTarget(), {
    document,
    navigator: { standalone: iphone ? true : undefined },
    matchMedia: () => ({ matches: android }),
    history: { length: historyLength, back: vi.fn() },
    navigation: canGoBack === undefined ? undefined : { canGoBack },
    location: { assign: vi.fn(), reload: vi.fn() },
    visualViewport: { scale },
    scrollY,
  });
}

function page(main = "<p>內容</p>", header = "") {
  document.body.innerHTML = `
    <div id="pwa-pull" hidden aria-hidden="true"></div>
    <header>${header}<button id="pwa-back" type="button" hidden>上一頁</button></header>
    <main>${main}</main>`;
}

// Pass several clientY values for several fingers.
function touch(win, type, ...clientYs) {
  const event = new Event(type);
  event.touches = clientYs.map((clientY) => ({ clientY }));
  win.dispatchEvent(event);
}

function pull(win, distance) {
  touch(win, "touchstart", 100);
  touch(win, "touchmove", 100 + distance);
}

const backButton = () => document.getElementById("pwa-back");
const hint = () => document.getElementById("pwa-pull");

beforeEach(() => page());

describe("outside the home-screen app", () => {
  // 1
  it("keeps the back button hidden and ignores pulling", () => {
    const win = fakeWindow({ iphone: false });
    setUpPwaNav(win);
    pull(win, PULL_THRESHOLD + 50);
    touch(win, "touchend");
    expect(backButton().hidden).toBe(true);
    expect(hint().hidden).toBe(true);
    expect(win.location.reload).not.toHaveBeenCalled();
  });
});

describe("back button", () => {
  afterEach(() => vi.useRealTimers());

  // 2
  it.each([
    ["iPhone", { iphone: true }],
    ["Android", { iphone: false, android: true }],
  ])("shows in the %s home-screen app", (_, options) => {
    setUpPwaNav(fakeWindow(options));
    expect(backButton().hidden).toBe(false);
  });

  it("does nothing on a page without the button (home page)", () => {
    document.getElementById("pwa-back").remove();
    expect(() => setUpPwaNav(fakeWindow())).not.toThrow();
  });

  // 4. The answer page's earlier questions are entries in the same page (pushState), and a
  // slow server delays the next page: either way going back must not end on the home page.
  it.each([
    ["the Navigation API", { canGoBack: true }],
    ["history.length", { historyLength: 2 }],
  ])("goes to the previous page, judged by %s", (_, options) => {
    vi.useFakeTimers();
    const win = fakeWindow(options);
    setUpPwaNav(win);
    backButton().click();
    vi.runAllTimers();
    expect(win.history.back).toHaveBeenCalledOnce();
    expect(win.location.assign).not.toHaveBeenCalled();
  });

  // 5
  it("goes home when the app opened on this page", () => {
    const win = fakeWindow({ historyLength: 1 });
    setUpPwaNav(win);
    backButton().click();
    expect(win.history.back).not.toHaveBeenCalled();
    expect(win.location.assign).toHaveBeenCalledWith("/");
  });

  // 5: after an iPhone reload the first page in the history may not be the home page.
  it("goes home when the Navigation API says there is nothing to go back to", () => {
    const win = fakeWindow({ historyLength: 3, canGoBack: false });
    setUpPwaNav(win);
    backButton().click();
    expect(win.history.back).not.toHaveBeenCalled();
    expect(win.location.assign).toHaveBeenCalledWith("/");
  });
});

describe("pull to refresh", () => {
  // 6
  it("reloads after pulling past the threshold from the top", () => {
    const win = fakeWindow();
    setUpPwaNav(win);
    pull(win, PULL_THRESHOLD / 2);
    expect(hint().hidden).toBe(false);
    expect(hint().textContent).toBe("往下拉重新整理");
    touch(win, "touchmove", 100 + PULL_THRESHOLD);
    expect(hint().textContent).toBe("放開重新整理");
    touch(win, "touchend");
    expect(win.location.reload).toHaveBeenCalledOnce();
  });

  // 7
  it("does not reload when let go too early", () => {
    const win = fakeWindow();
    setUpPwaNav(win);
    pull(win, PULL_THRESHOLD - 1);
    touch(win, "touchend");
    expect(hint().hidden).toBe(true);
    expect(win.location.reload).not.toHaveBeenCalled();
  });

  it("does not reload when the touch is cancelled", () => {
    const win = fakeWindow();
    setUpPwaNav(win);
    pull(win, PULL_THRESHOLD + 50);
    touch(win, "touchcancel");
    touch(win, "touchend");
    expect(hint().hidden).toBe(true);
    expect(win.location.reload).not.toHaveBeenCalled();
  });

  it("starts each pull afresh", () => {
    const win = fakeWindow();
    setUpPwaNav(win);
    pull(win, PULL_THRESHOLD + 50);
    touch(win, "touchcancel");
    touch(win, "touchstart", 100);
    touch(win, "touchend");
    expect(win.location.reload).not.toHaveBeenCalled();
  });

  // 8
  it("leaves ordinary scrolling alone when the page is not at the top", () => {
    const win = fakeWindow({ scrollY: 200 });
    setUpPwaNav(win);
    pull(win, PULL_THRESHOLD + 50);
    expect(hint().hidden).toBe(true);
    touch(win, "touchend");
    expect(win.location.reload).not.toHaveBeenCalled();
  });

  // Pinch zoom moves the fingers apart, so one of them may travel down past the threshold.
  it("ignores a touch that starts with two fingers", () => {
    const win = fakeWindow();
    setUpPwaNav(win);
    touch(win, "touchstart", 100, 300);
    touch(win, "touchmove", 100 + PULL_THRESHOLD + 50, 250);
    expect(hint().hidden).toBe(true);
    touch(win, "touchend");
    expect(win.location.reload).not.toHaveBeenCalled();
  });

  it("cancels the pull when a second finger joins", () => {
    const win = fakeWindow();
    setUpPwaNav(win);
    pull(win, PULL_THRESHOLD / 2);
    touch(win, "touchmove", 100 + PULL_THRESHOLD + 50, 300);
    expect(hint().hidden).toBe(true);
    touch(win, "touchmove", 100 + PULL_THRESHOLD + 50);
    touch(win, "touchend");
    expect(win.location.reload).not.toHaveBeenCalled();
  });

  it("is off while the page is zoomed in", () => {
    const win = fakeWindow({ scale: 2 });
    setUpPwaNav(win);
    pull(win, PULL_THRESHOLD + 50);
    expect(hint().hidden).toBe(true);
    touch(win, "touchend");
    expect(win.location.reload).not.toHaveBeenCalled();
  });

  it("shows no hint while scrolling up from the top", () => {
    const win = fakeWindow();
    setUpPwaNav(win);
    pull(win, -50);
    expect(hint().hidden).toBe(true);
  });

  // 9: the questionnaire form, and the audiogram input's selects and checkboxes (no <form>).
  it.each([
    ["a form", "<form><button>送出</button></form>"],
    ["an input", '<input type="checkbox">'],
    ["a select", "<select><option>40</option></select>"],
    ["a textarea", "<textarea></textarea>"],
  ])("is off when the page content has %s", (_, main) => {
    const win = fakeWindow();
    setUpPwaNav(win);
    page(main); // React may draw the inputs after the script runs.
    pull(win, PULL_THRESHOLD + 50);
    expect(hint().hidden).toBe(true);
    touch(win, "touchend");
    expect(win.location.reload).not.toHaveBeenCalled();
  });

  // 9b
  it("still works when the only form is the log-out button in the header", () => {
    page("<p>我的紀錄</p>", '<form id="logout-form"><button>登出</button></form>');
    const win = fakeWindow();
    setUpPwaNav(win);
    pull(win, PULL_THRESHOLD + 50);
    touch(win, "touchend");
    expect(win.location.reload).toHaveBeenCalledOnce();
  });
});
