import { beforeEach, describe, expect, it } from "vitest";

import { playJourneyOnce, setUpJourneySteps } from "./care-journey.js";

// #459 (the owner's pick I1 + I2 on the step interactions page, ADR 0028's 2026-11-12 exception).

function fakeWindow({ reduce = false } = {}) {
  window.sessionStorage.clear();
  document.documentElement.className = "";
  window.matchMedia = (query) => ({
    matches: query === "(prefers-reduced-motion: reduce)" && reduce,
  });
  return window;
}

describe("playJourneyOnce", () => {
  it("plays the journey's entrance on the tab's first visit", () => {
    const win = fakeWindow();
    playJourneyOnce(win);
    expect(document.documentElement.classList.contains("journey-plays")).toBe(true);
  });

  it("does not play it again later in the same tab", () => {
    const win = fakeWindow();
    playJourneyOnce(win);
    document.documentElement.className = "";
    playJourneyOnce(win);
    expect(document.documentElement.classList.contains("journey-plays")).toBe(false);
  });

  it("never plays with reduced motion, nor counts as played", () => {
    const win = fakeWindow({ reduce: true });
    playJourneyOnce(win);
    expect(document.documentElement.classList.contains("journey-plays")).toBe(false);
    expect(win.sessionStorage.length).toBe(0);
  });
});

describe("setUpJourneySteps", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <ol class="journey-steps">
        <li><details class="journey-about"><summary>1</summary><p>一</p></details></li>
        <li><details class="journey-about"><summary>2</summary><p>二</p></details></li>
        <li><div class="journey-card">現在這一步</div></li>
        <li><details class="journey-about"><summary>4</summary><p>四</p></details></li>
      </ol>`;
    setUpJourneySteps(document);
  });

  const steps = () => [...document.querySelectorAll(".journey-about")];
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

  it("leaves the 現在這一步's card as it is", async () => {
    await open(0);
    expect(document.querySelector(".journey-card").textContent).toBe("現在這一步");
  });

  it("closes an open step on its own", async () => {
    await open(0);
    steps()[0].open = false;
    await settle();
    expect(steps().map((step) => step.open)).toEqual([false, false, false]);
  });
});
