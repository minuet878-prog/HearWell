import { describe, expect, it, vi } from "vitest";

import { setUpSwitchSlide } from "./switch-slide.js";

// #334 (spec #326 D3, ADR 0028): site.css lets every change of page run a view transition in
// which only the switch's pill moves; this script skips all but those the switch itself starts.
// Each test gets its own document, so listeners from earlier tests never answer.
let doc;
let win;

function page() {
  doc = document.implementation.createHTMLDocument("");
  doc.body.innerHTML = `
    <nav aria-label="主要導覽"><a href="/">首頁</a></nav>
    <main>
      <nav class="records-switch" aria-label="紀錄種類">
        <a href="/my_hearing?view=questionnaires" aria-current="page">問卷</a>
        <a href="/audiograms"><span>聽力圖</span></a>
      </nav>
      <nav class="ear-switch" aria-label="選耳朵">
        <a href="?ear=right" aria-current="true">右耳</a>
        <a href="?ear=left">左耳</a>
      </nav>
      <a class="link-card" href="/audiograms/1">2026/09/28</a>
      <form><button type="submit">比較</button></form>
    </main>`;
  win = Object.assign(new EventTarget(), { document: doc });
  setUpSwitchSlide(win);
}

function click(selector) {
  doc.querySelector(selector).dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

// The browser fires pageswap on the page being left, just before the next one shows.
function leave() {
  const viewTransition = { skipTransition: vi.fn() };
  win.dispatchEvent(Object.assign(new Event("pageswap"), { viewTransition }));
  return viewTransition.skipTransition;
}

describe("the pill slides", () => {
  it("when the other side of 問卷｜聽力圖 is pressed", () => {
    page();
    click(".records-switch a:not([aria-current]) span");
    expect(leave()).not.toHaveBeenCalled();
  });

  it("when the other ear is pressed", () => {
    page();
    click('.ear-switch a[href="?ear=left"]');
    expect(leave()).not.toHaveBeenCalled();
  });
});

describe("every other change of page has no transition", () => {
  it.each([
    ["a bottom tab", 'nav[aria-label="主要導覽"] a'],
    ["a card", ".link-card"],
  ])("pressing %s", (_, selector) => {
    page();
    click(selector);
    expect(leave()).toHaveBeenCalledOnce();
  });

  it("sending a form, even after pressing the switch", () => {
    page();
    click(".records-switch a:not([aria-current])");
    doc.querySelector("form").dispatchEvent(new SubmitEvent("submit", { bubbles: true }));
    expect(leave()).toHaveBeenCalledOnce();
  });

  it("the back button, with nothing pressed", () => {
    page();
    expect(leave()).toHaveBeenCalledOnce();
  });

  it("the back button on a page that came back from the cache after its switch was pressed", () => {
    page();
    click(".records-switch a:not([aria-current])");
    win.dispatchEvent(new Event("pageshow"));
    expect(leave()).toHaveBeenCalledOnce();
  });

  it("a press elsewhere after the switch", () => {
    page();
    click(".records-switch a:not([aria-current])");
    click(".link-card");
    expect(leave()).toHaveBeenCalledOnce();
  });
});

it("leaves a page without any transition alone", () => {
  page();
  expect(() => win.dispatchEvent(new Event("pageswap"))).not.toThrow();
});
