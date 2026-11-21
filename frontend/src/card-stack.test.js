import { beforeEach, describe, expect, it } from "vitest";

import { DRAG_THRESHOLD, setUpCardStack } from "./card-stack.js";

// #753 (spec #741 acceptance 46, 56; P3, P4): the stacked cards, as the questionnaires page
// writes them (questionnaire.html, card_stack_controls.html). jsdom has no layout, so a card's
// place shows in its attributes: the current one is the one not aria-hidden.
function fakeWindow({ reducedMotion = false } = {}) {
  return {
    matchMedia: (query) => ({
      matches: query === "(prefers-reduced-motion: reduce)" && reducedMotion,
    }),
  };
}

const NAMES = ["HHIE-S", "SSQ12-TW", "THI"];

function page(count = 3) {
  const cards = NAMES.slice(0, count)
    .map(
      (name, i) => `
      <article class="hero-card card-stack-card" role="group" aria-roledescription="卡片"
        aria-label="第 ${i + 1} 張，共 ${count} 張：${name}">
        <h2>${name}</h2><a class="btn" href="/questionnaire/${i + 1}">開始作答</a>
      </article>`,
    )
    .join("");
  document.body.innerHTML = `
    <section class="card-stack" aria-roledescription="輪播" aria-label="問卷卡片">
      <div class="card-stack-cards">${cards}</div>
      <div class="card-stack-controls" hidden>
        <button type="button" class="card-stack-prev" aria-label="上一張"></button>
        <div class="card-stack-where">
          <p class="card-stack-position" aria-live="polite">第 1 張，共 ${count} 張</p>
          <span class="card-stack-dots" aria-hidden="true">${"<span></span>".repeat(count)}</span>
        </div>
        <button type="button" class="card-stack-next" aria-label="下一張"></button>
      </div>
    </section>`;
  return document.querySelector(".card-stack");
}

const stack = () => document.querySelector(".card-stack");
const cards = () => [...document.querySelectorAll(".card-stack-card")];
const current = () => cards().find((card) => !card.hasAttribute("aria-hidden"));
const shown = () => current().querySelector("h2").textContent;
const position = () => document.querySelector(".card-stack-position").textContent;
const prev = () => document.querySelector(".card-stack-prev");
const next = () => document.querySelector(".card-stack-next");

// The button is held from pointerdown until pointerup.
function pointer(type, x, target = current()) {
  const buttons = type === "pointerup" ? 0 : 1;
  target.dispatchEvent(
    new PointerEvent(type, { bubbles: true, clientX: x, clientY: 100, pointerId: 1, buttons }),
  );
}

function drag(from, to) {
  pointer("pointerdown", from);
  pointer("pointermove", (from + to) / 2);
  pointer("pointermove", to);
  pointer("pointerup", to);
}

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("setUpCardStack", () => {
  it("shows the buttons and the first card, the others out of reach", () => {
    setUpCardStack(page(), fakeWindow());
    expect(document.querySelector(".card-stack-controls").hidden).toBe(false);
    expect(shown()).toBe("HHIE-S");
    expect(position()).toBe("第 1 張，共 3 張");
    expect(prev().disabled).toBe(true);
    expect(next().disabled).toBe(false);
    for (const card of cards().slice(1)) {
      expect(card.getAttribute("aria-hidden")).toBe("true");
      expect(card.inert).toBe(true);
    }
    expect(current().inert).toBe(false);
  });

  it("keeps each card's name and place for screen readers", () => {
    setUpCardStack(page(), fakeWindow());
    expect(cards().map((card) => card.getAttribute("aria-label"))).toEqual([
      "第 1 張，共 3 張：HHIE-S",
      "第 2 張，共 3 張：SSQ12-TW",
      "第 3 張，共 3 張：THI",
    ]);
  });

  it("goes to the next card with › and back with ‹, stopping at either end", () => {
    setUpCardStack(page(), fakeWindow());
    next().click();
    expect(shown()).toBe("SSQ12-TW");
    expect(position()).toBe("第 2 張，共 3 張");
    expect(prev().disabled).toBe(false);
    next().click();
    expect(shown()).toBe("THI");
    expect(next().disabled).toBe(true);
    prev().click();
    expect(shown()).toBe("SSQ12-TW");
  });

  it("takes the focus from a card going behind to the one coming to the front", () => {
    setUpCardStack(page(), fakeWindow());
    current().querySelector("a").focus();
    current().dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    expect(document.activeElement).toBe(current().querySelector("a"));
    expect(shown()).toBe("SSQ12-TW");
  });

  it("changes card with the arrow keys", () => {
    setUpCardStack(page(), fakeWindow());
    current().dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    expect(shown()).toBe("SSQ12-TW");
    current().dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
    expect(shown()).toBe("HHIE-S");
  });

  it("goes to the next card when dragged left past the threshold, and back when dragged right", () => {
    setUpCardStack(page(), fakeWindow());
    drag(300, 300 - DRAG_THRESHOLD - 10);
    expect(shown()).toBe("SSQ12-TW");
    drag(100, 100 + DRAG_THRESHOLD + 10);
    expect(shown()).toBe("HHIE-S");
  });

  it("snaps back when the drag is too short", () => {
    setUpCardStack(page(), fakeWindow());
    pointer("pointerdown", 300);
    pointer("pointermove", 300 - DRAG_THRESHOLD + 10);
    // The card follows the finger while it is down.
    expect(stack().style.getPropertyValue("--card-stack-drag")).toBe(`${-DRAG_THRESHOLD + 10}px`);
    pointer("pointerup", 300 - DRAG_THRESHOLD + 10);
    expect(shown()).toBe("HHIE-S");
    expect(stack().style.getPropertyValue("--card-stack-drag")).toBe("");
  });

  it("does not drag under a mouse moved with no button held", () => {
    // A press let go off the cards never reaches them as a pointerup.
    setUpCardStack(page(), fakeWindow());
    pointer("pointerdown", 300);
    current().dispatchEvent(
      new PointerEvent("pointermove", { bubbles: true, clientX: 200, pointerId: 1, buttons: 0 }),
    );
    expect(stack().style.getPropertyValue("--card-stack-drag")).toBe("");
  });

  it("does not open a card's link at the end of a drag, but does on a plain tap", () => {
    setUpCardStack(page(), fakeWindow());
    const link = current().querySelector("a");
    pointer("pointerdown", 300, link);
    pointer("pointermove", 270, link);
    pointer("pointerup", 270, link);
    const afterDrag = new MouseEvent("click", { bubbles: true, cancelable: true });
    link.dispatchEvent(afterDrag);
    expect(afterDrag.defaultPrevented).toBe(true);
    pointer("pointerdown", 300, link);
    pointer("pointerup", 300, link);
    const tap = new MouseEvent("click", { bubbles: true, cancelable: true });
    link.dispatchEvent(tap);
    expect(tap.defaultPrevented).toBe(false);
  });

  it("changes card without sliding under reduced motion", () => {
    setUpCardStack(page(), fakeWindow({ reducedMotion: true }));
    pointer("pointerdown", 300);
    pointer("pointermove", 200);
    expect(stack().style.getPropertyValue("--card-stack-drag")).toBe("");
    pointer("pointerup", 200);
    expect(shown()).toBe("SSQ12-TW");
  });

  it("says so from each card that comes to the front, for in-view.js to play its drawing", () => {
    // #754: the 了解 page's cards each have a drawing that plays once, at the front.
    const fronts = [];
    const heard = (event) => fronts.push(event.target.querySelector("h2").textContent);
    document.addEventListener("card-stack-show", heard);
    setUpCardStack(page(), fakeWindow());
    next().click();
    next().click();
    prev().click();
    document.removeEventListener("card-stack-show", heard);
    expect(fronts).toEqual(["HHIE-S", "SSQ12-TW", "THI", "SSQ12-TW"]);
  });

  it("leaves a single card alone", () => {
    setUpCardStack(page(1), fakeWindow());
    expect(document.querySelector(".card-stack-controls").hidden).toBe(true);
    expect(stack().hasAttribute("data-ready")).toBe(false);
  });
});
