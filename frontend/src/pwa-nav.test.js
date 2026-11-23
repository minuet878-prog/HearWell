import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PULL_SHOW_AFTER, PULL_THRESHOLD, setUpPwaNav } from "./pwa-nav.js";

// Spec docs/specs/phase-10/phase10_pwa_back_refresh.md. A stand-in window so tests can see
// reload() calls, which jsdom cannot perform.
function fakeWindow({
  iphone = true,
  android = false,
  scale = 1,
  scrollY = 0,
} = {}) {
  return Object.assign(new EventTarget(), {
    document,
    navigator: { standalone: iphone ? true : undefined },
    matchMedia: () => ({ matches: android }),
    location: { reload: vi.fn() },
    visualViewport: { scale },
    scrollY,
  });
}

function page(main = "<p>內容</p>") {
  document.body.innerHTML = `
    <div id="pwa-pull" hidden aria-hidden="true"></div>
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

const hint = () => document.getElementById("pwa-pull");

beforeEach(() => page());

describe("outside the home-screen app", () => {
  // 1
  it("ignores pulling", () => {
    const win = fakeWindow({ iphone: false });
    setUpPwaNav(win);
    pull(win, PULL_THRESHOLD + 50);
    touch(win, "touchend");
    expect(hint().hidden).toBe(true);
    expect(win.location.reload).not.toHaveBeenCalled();
  });
});

// Ticket #160: the home page's "加到手機主畫面" card is pointless inside the app.
describe("items marked data-hide-in-app", () => {
  const item = () => document.querySelector("[data-hide-in-app]");
  beforeEach(() => page('<ul><li>記錄聽力圖</li><li data-hide-in-app>加到手機主畫面</li></ul>'));

  it.each([
    ["iPhone", { iphone: true }],
    ["Android", { iphone: false, android: true }],
  ])("are hidden in the %s home-screen app", (_, options) => {
    setUpPwaNav(fakeWindow(options));
    expect(item().hidden).toBe(true);
  });

  it("stay visible in a browser tab", () => {
    setUpPwaNav(fakeWindow({ iphone: false }));
    expect(item().hidden).toBe(false);
  });
});

// The server reads it when a LINE trip starts (screening/oidc.py HOME_SCREEN_APP).
describe("the home_screen_app cookie", () => {
  afterEach(() => {
    document.cookie = "home_screen_app=; path=/; max-age=0";
  });

  it("is left in the iPhone home-screen app", () => {
    setUpPwaNav(fakeWindow({ iphone: true }));
    expect(document.cookie).toContain("home_screen_app=1");
  });

  // An Android home-screen app shares Chrome's cookies, so LINE's auto login comes back to it.
  it.each([
    ["the Android home-screen app", { iphone: false, android: true }],
    ["a browser tab", { iphone: false }],
  ])("is not left in %s", (_, options) => {
    setUpPwaNav(fakeWindow(options));
    expect(document.cookie).not.toContain("home_screen_app");
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

  it("keeps the hint hidden for tiny downward jitter under the show threshold", () => {
    const win = fakeWindow();
    setUpPwaNav(win);
    pull(win, PULL_SHOW_AFTER - 1);
    expect(hint().hidden).toBe(true);
  });

  it("cancels the pull when the finger swipes sideways", () => {
    const win = fakeWindow();
    setUpPwaNav(win);
    const start = new Event("touchstart");
    start.touches = [{ clientX: 200, clientY: 100 }];
    win.dispatchEvent(start);
    const move = new Event("touchmove");
    move.touches = [{ clientX: 80, clientY: 100 + PULL_THRESHOLD + 10 }];
    win.dispatchEvent(move);
    expect(hint().hidden).toBe(true);
    touch(win, "touchend");
    expect(win.location.reload).not.toHaveBeenCalled();
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
});
