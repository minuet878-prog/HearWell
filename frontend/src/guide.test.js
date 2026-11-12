import { beforeEach, describe, expect, it } from "vitest";

import { openFoldsForJump, playRouteOnce, setUpRouteStops } from "./guide.js";

// #467: 我的選配指引's 選配路線 (the owner's pick I1 + I2, ADR 0028's 2026-11-12 exception) and
// the chapters' folds (H2), which open where a jump lands.

function fakeWindow({ reduce = false, hash = "" } = {}) {
  window.sessionStorage.clear();
  document.documentElement.className = "";
  window.matchMedia = (query) => ({
    matches: query === "(prefers-reduced-motion: reduce)" && reduce,
  });
  window.history.replaceState(null, "", `/guide${hash}`);
  return window;
}

const route = (extra = "") => `
  <ol class="route">
    <li class="route-stop is-done"><details class="route-about"><summary>1</summary><p>一</p></details></li>
    <li class="route-stop is-here${extra}"><div class="route-card">您在這裡</div></li>
    <li class="route-stop"><details class="route-about"><summary>3</summary><p>三</p></details></li>
    <li class="route-stop"><details class="route-about"><summary>4</summary><p>四</p></details></li>
  </ol>`;

const plays = () => document.documentElement.classList.contains("route-plays");

describe("playRouteOnce", () => {
  beforeEach(() => {
    document.body.innerHTML = route();
  });

  it("plays the route's entrance on the tab's first visit", () => {
    playRouteOnce(fakeWindow());
    expect(plays()).toBe(true);
  });

  it("does not play it again later in the same tab", () => {
    const win = fakeWindow();
    playRouteOnce(win);
    document.documentElement.className = "";
    playRouteOnce(win);
    expect(plays()).toBe(false);
  });

  it("never plays with reduced motion, nor counts as played", () => {
    const win = fakeWindow({ reduce: true });
    playRouteOnce(win);
    expect(plays()).toBe(false);
    expect(win.sessionStorage.length).toBe(0);
  });

  it("waits while a stop just answered draws its own tick", () => {
    document.body.innerHTML = route().replace('class="route-stop is-done"', 'class="route-stop is-done-now"');
    const win = fakeWindow();
    playRouteOnce(win);
    expect(plays()).toBe(false);
    expect(win.sessionStorage.length).toBe(0);
  });

  it("has nothing to play without a 目前這一站", () => {
    document.body.innerHTML = route().replace(" is-here", "");
    const win = fakeWindow();
    playRouteOnce(win);
    expect(plays()).toBe(false);
    expect(win.sessionStorage.length).toBe(0);
  });
});

describe("setUpRouteStops", () => {
  beforeEach(() => {
    document.body.innerHTML = route();
    setUpRouteStops(document);
  });

  const stops = () => [...document.querySelectorAll(".route-about")];
  const open = (index) =>
    new Promise((resolve) => {
      stops()[index].addEventListener("toggle", resolve, { once: true });
      stops()[index].open = true;
    });
  const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

  it("opens one stop at a time", async () => {
    await open(0);
    await open(2);
    await settle();
    expect(stops().map((stop) => stop.open)).toEqual([false, false, true]);
  });

  it("leaves the 您在這裡 card as it is", async () => {
    await open(1);
    expect(document.querySelector(".route-card").textContent).toBe("您在這裡");
  });
});

describe("openFoldsForJump", () => {
  // The folds come open in the page, so without JavaScript every part shows in full.
  beforeEach(() => {
    document.body.innerHTML = `
      <section><h2 id="who-title">我可以申請嗎？</h2><p>一句</p>
        <details data-guide-fold open><summary>看更多</summary><p>其他</p></details></section>
      <section><h2 id="steps-title">要怎麼辦？</h2><p>一句</p>
        <details data-guide-fold open><summary>看更多</summary><p>步驟</p></details></section>
      <section><h2 id="amount-title">可以補助多少錢？</h2>
        <details data-guide-fold open><summary>看更多</summary><h3 id="inside">裡面</h3></details></section>`;
  });

  const folds = () => [...document.querySelectorAll("[data-guide-fold]")].map((f) => f.open);

  it("folds every part away when the page is opened at its top", () => {
    openFoldsForJump(fakeWindow());
    expect(folds()).toEqual([false, false, false]);
  });

  it("keeps the part a jump lands on open", () => {
    openFoldsForJump(fakeWindow({ hash: "#steps-title" }));
    expect(folds()).toEqual([false, true, false]);
  });

  it("keeps the fold open when the jump lands inside it", () => {
    openFoldsForJump(fakeWindow({ hash: "#inside" }));
    expect(folds()).toEqual([false, false, true]);
  });

  it("opens the part a later jump in the page lands on", () => {
    const win = fakeWindow();
    openFoldsForJump(win);
    win.history.replaceState(null, "", "/guide#who-title");
    win.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(folds()).toEqual([true, false, false]);
  });

  it("shows the folds once they are sorted", () => {
    const win = fakeWindow({ hash: "#steps-title" });
    document.documentElement.classList.add("guide-folds-pending");
    openFoldsForJump(win);
    expect(document.documentElement.classList.contains("guide-folds-pending")).toBe(false);
  });
});
