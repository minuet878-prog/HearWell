import { beforeEach, describe, expect, it } from "vitest";

import { openOneAtATime, playOnceATab } from "./step-list.js";

// Steps on a line: the home page's 照顧旅程 (#459) and my guide's 選配路線 (#467), the owner's
// pick I1 + I2 on the step interactions page (ADR 0028's 2026-11-12 exception).

function fakeWindow({ reduce = false } = {}) {
  window.sessionStorage.clear();
  document.documentElement.className = "";
  window.matchMedia = (query) => ({
    matches: query === "(prefers-reduced-motion: reduce)" && reduce,
  });
  return window;
}

const plays = (name) => document.documentElement.classList.contains(name);

describe("playOnceATab", () => {
  it("plays the entrance on the tab's first visit", () => {
    playOnceATab(fakeWindow(), "journey-played", "journey-plays");
    expect(plays("journey-plays")).toBe(true);
  });

  it("does not play it again later in the same tab", () => {
    const win = fakeWindow();
    playOnceATab(win, "journey-played", "journey-plays");
    document.documentElement.className = "";
    playOnceATab(win, "journey-played", "journey-plays");
    expect(plays("journey-plays")).toBe(false);
  });

  it("never plays with reduced motion, nor counts as played", () => {
    const win = fakeWindow({ reduce: true });
    playOnceATab(win, "journey-played", "journey-plays");
    expect(plays("journey-plays")).toBe(false);
    expect(win.sessionStorage.length).toBe(0);
  });

  it("keeps each list's first visit its own", () => {
    const win = fakeWindow();
    playOnceATab(win, "journey-played", "journey-plays");
    playOnceATab(win, "route-played", "route-plays");
    expect(plays("journey-plays")).toBe(true);
    expect(plays("route-plays")).toBe(true);
  });
});

describe("openOneAtATime", () => {
  for (const [kind, list, item, card] of [
    ["照顧旅程", "journey-steps", "journey-about", "journey-card"],
    ["選配路線", "route", "route-about", "route-card"],
  ]) {
    describe(kind, () => {
      beforeEach(() => {
        document.body.innerHTML = `
          <ol class="${list}">
            <li><details class="${item}"><summary>1</summary><p>一</p></details></li>
            <li><details class="${item}"><summary>2</summary><p>二</p></details></li>
            <li><div class="${card}">現在</div></li>
            <li><details class="${item}"><summary>4</summary><p>四</p></details></li>
          </ol>`;
        openOneAtATime(document, `.${list}`, `.${item}`);
      });

      const steps = () => [...document.querySelectorAll(`.${item}`)];
      const open = (index) =>
        new Promise((resolve) => {
          steps()[index].addEventListener("toggle", resolve, { once: true });
          steps()[index].open = true;
        });
      // Each close sends its own toggle event; let them all arrive.
      const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

      it("opens one step at a time", async () => {
        await open(0);
        await open(1);
        await settle();
        expect(steps().map((step) => step.open)).toEqual([false, true, false]);
        await open(2);
        await settle();
        expect(steps().map((step) => step.open)).toEqual([false, false, true]);
      });

      it("leaves the current step's card as it is", async () => {
        await open(0);
        expect(document.querySelector(`.${card}`).textContent).toBe("現在");
      });

      it("closes an open step on its own", async () => {
        await open(0);
        steps()[0].open = false;
        await settle();
        expect(steps().map((step) => step.open)).toEqual([false, false, false]);
      });
    });
  }
});
