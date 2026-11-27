import { afterEach, describe, expect, it, vi } from "vitest";

import { saveGuestResult, showGuestResult } from "./guest-results.js";
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
// with a scroll event, and runs animation frames only when the test steps its clock. Each test's
// page shares one document body, so what one test set up watching it stops after it.
const observers = [];
afterEach(() => {
  for (const observer of observers.splice(0)) observer.disconnect();
});

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
    MutationObserver: class extends window.MutationObserver {
      constructor(callback) {
        super(callback);
        observers.push(this);
      }
    },
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

  it("waits for a guide card stamp to scroll inside the row before playing it once", () => {
    page(`<ol class="guide-cards"><li><span data-play-in-view>已完成</span></li></ol>`);
    const row = document.querySelector(".guide-cards");
    const stamp = row.querySelector("[data-play-in-view]");
    row.getBoundingClientRect = () => ({ left: 16, right: 304 });
    const scrollTo = (left) => {
      stamp.getBoundingClientRect = () => ({ top: 100, bottom: 160, left, right: left + 80 });
      row.dispatchEvent(new Event("scroll"));
    };
    scrollTo(320);
    setUpPlayInView(fakeWindow());
    expect(stamp.hasAttribute("data-in-view")).toBe(false);
    scrollTo(260);
    expect(stamp.hasAttribute("data-in-view")).toBe(false);
    scrollTo(210);
    expect(stamp.hasAttribute("data-in-view")).toBe(true);
    scrollTo(320);
    expect(stamp.hasAttribute("data-in-view")).toBe(true);
  });

  it("holds a drawing on a stacked card behind the front until the card comes forward", () => {
    // #754: the 了解 page's cards behind the front one are inert; card-stack.js says when one
    // comes to the front.
    page(`
      <article class="card-stack-card"><svg class="play-once-wave" data-play-in-view></svg></article>
      <article class="card-stack-card" inert><svg class="play-once-ring" data-play-in-view></svg></article>`);
    const [front, behind] = document.querySelectorAll(".card-stack-card");
    const drawing = (card) => card.querySelector("[data-play-in-view]");
    setUpPlayInView(fakeWindow());
    expect(drawing(front).hasAttribute("data-in-view")).toBe(true);
    expect(drawing(behind).hasAttribute("data-in-view")).toBe(false);

    behind.removeAttribute("inert");
    behind.dispatchEvent(new Event("card-stack-show", { bubbles: true }));
    expect(drawing(behind).hasAttribute("data-in-view")).toBe(true);
  });

  it("holds a drawing in a shut fold, whose would-be place is in view, until the fold opens", () => {
    // #780: my guide's meters in 看聽力圖數值與計算公式. A shut <details> still lays its
    // contents out when asked, so their box alone would say in view.
    page(`<details><summary>看聽力圖數值與計算公式</summary><div class="meter" data-play-in-view></div></details>`);
    const fold = document.querySelector("details");
    const meter = document.querySelector("[data-play-in-view]");
    const win = fakeWindow();
    setUpPlayInView(win);
    expect(meter.hasAttribute("data-in-view")).toBe(false);

    fold.open = true;
    win.dispatchEvent(new Event("resize")); // the page grows as it opens
    expect(meter.hasAttribute("data-in-view")).toBe(true);
  });

  it("plays a drawing in a shut fold's summary, which shows", () => {
    // The home's 照顧旅程: step 1's row is a fold's summary.
    page(`<details><summary data-play-in-view>聽力對生活的影響</summary><p>說明</p></details>`);
    setUpPlayInView(fakeWindow());
    expect(document.querySelector("summary").hasAttribute("data-in-view")).toBe(true);
  });

  it("disconnects ResizeObserver immediately when no animations are waiting on initial load (D4)", () => {
    page(`<p>沒有動畫的頁面</p>`);
    const win = fakeWindow();
    let disconnected = false;
    win.ResizeObserver = class {
      observe() {}
      disconnect() {
        disconnected = true;
      }
    };
    setUpPlayInView(win);
    expect(disconnected).toBe(true);
  });
});

// Codex cross review of #741, item 2: the guest result page puts its result in after this set up
// (guest-results.js fetches the score first), and layout.html's 3-second fallback was called off
// then, so a gauge put in later has to be picked up, or it holds its first frame for ever.
describe("setUpPlayInView: elements put in after it set up", () => {
  afterEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  // MutationObserver says what was put in once the current task's microtasks run.
  const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
  const GAUGE = `<div class="gauge" data-play-in-view><svg><path class="play-once-gauge"/></svg></div>
    <p>總分 <span data-count-up>16</span> 分</p>
    <details data-guest-clear><summary>清除這次結果</summary><p data-guest-clear-question></p>
      <button type="button" data-guest-clear-yes>清除</button>
      <button type="button" data-guest-clear-no>不要</button></details>`;

  async function guestResultPage(win) {
    page(`<div id="guest-result" data-code="hhie-s" data-score-url="/api/guest-scores/" data-home-url="/">
      <div data-guest-shown hidden><h1 class="bird-title"></h1><div data-guest-section></div></div>
      <p role="alert" data-guest-error></p></div>`);
    setUpPlayInView(win);
    saveGuestResult({
      code: "hhie-s", questionnaireId: 1, answers: [{ question: 11, score: 4 }], wearing: false,
      key: "9b2f6a4e-1c3d-4e5f-8a9b-0c1d2e3f4a5b", finishedAt: Date.now(), total: 16,
      level: { code: "mild_to_moderate", text: "輕度到中度影響", color: "mild_to_moderate" },
    });
    const body = { html: GAUGE };
    const fetchScore = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    await showGuestResult({ root: document.getElementById("guest-result"), fetchScore, navigate: vi.fn() });
    await settle();
  }

  it("plays the guest result's gauge and counts its number once they are put in", async () => {
    const win = fakeWindow();
    await guestResultPage(win);
    expect(document.querySelector(".gauge").hasAttribute("data-in-view")).toBe(true);
    win.frameAt(1000);
    win.frameAt(1900);
    expect(number().hasAttribute("data-count-done")).toBe(true);
  });

  it("waits for one put in below the screen, and plays nothing put in again a second time", async () => {
    const win = fakeWindow();
    page("");
    setUpPlayInView(win);
    const box = document.createElement("div");
    box.setAttribute("data-play-in-view", "");
    box.getBoundingClientRect = () => ({ top: 1200, bottom: 1260 });
    document.querySelector("main").append(box);
    await settle();
    expect(box.hasAttribute("data-in-view")).toBe(false);
    win.scrollElementTo(box, 300);
    expect(box.hasAttribute("data-in-view")).toBe(true);

    // Played already: put in again (moved), it stays played and counts nothing.
    const played = document.createElement("span");
    played.setAttribute("data-count-up", "");
    played.setAttribute("data-count-done", "");
    played.textContent = "20";
    document.querySelector("main").append(played, box);
    await settle();
    win.frameAt(1000);
    expect(played.hasAttribute("data-count-now")).toBe(false);
    expect(played.hasAttribute("data-in-view")).toBe(false);
  });

  it("shows a number put in later at its end at once with reduced motion", async () => {
    const win = fakeWindow({ reducedMotion: true });
    await guestResultPage(win);
    expect(number().hasAttribute("data-count-done")).toBe(true);
    win.frameAt(1000);
    expect(number().hasAttribute("data-count-now")).toBe(false);
  });
});
