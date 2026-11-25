import { beforeEach, describe, expect, it } from "vitest";

import { openFoldsForJump } from "./guide.js";

// #467: the chapters' folds (H2), which open where a jump lands. #779: my guide's 選配路線
// entrance went with the route.

function fakeWindow({ reduce = false, hash = "" } = {}) {
  window.sessionStorage.clear();
  document.documentElement.className = "";
  window.matchMedia = (query) => ({
    matches: query === "(prefers-reduced-motion: reduce)" && reduce,
  });
  window.history.replaceState(null, "", `/guide${hash}`);
  return window;
}

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
