import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { showGuestHome } from "./guest-home.js";
import { saveGuestResult } from "./guest-results.js";

// #499 (spec #492 acceptance 21, the #493 mockup's A1): on the logged-out home, the guest results
// kept in this browser, each a tile in its level's colour that opens its guest result page.
const NOW = Date.parse("2026-11-13T10:00:00+08:00");
const DAY = 24 * 60 * 60 * 1000;
const QUESTIONNAIRES = {
  "hhie-s": { topic: "聽力對生活的影響", url: "/guest/result/hhie-s" },
  "hhia-s": { topic: "聽力對生活的影響", url: "/guest/result/hhia-s" },
};

function guestResult(overrides = {}) {
  return {
    code: "hhie-s",
    questionnaireId: 1,
    answers: [{ question: 11, score: 4 }],
    wearing: false,
    key: "9b2f6a4e-1c3d-4e5f-8a9b-0c1d2e3f4a5b",
    finishedAt: NOW - 2 * DAY,
    total: 14,
    level: { code: "mild_to_moderate", text: "輕度到中度影響", color: "mild_to_moderate" },
    ...overrides,
  };
}

let root;
beforeEach(() => {
  document.body.innerHTML = '<main><div id="guest-home" hidden></div><h1>從一份問卷開始</h1></main>';
  root = document.getElementById("guest-home");
});

afterEach(() => localStorage.clear());

const show = () => showGuestHome({ root, questionnaires: QUESTIONNAIRES, now: NOW });
const lines = (tile) => [...tile.children].map((part) => part.textContent);

describe("showGuestHome", () => {
  it("leaves the place empty and hidden without a guest result", () => {
    show();
    expect(root.hidden).toBe(true);
    expect(root.children).toHaveLength(0);
  });

  it("shows one result's day, level and days left, the whole tile a link to its page", () => {
    saveGuestResult(guestResult());
    show();
    expect(root.hidden).toBe(false);
    const tiles = root.querySelectorAll("a");
    expect(tiles).toHaveLength(1);
    expect(tiles[0].getAttribute("href")).toBe("/guest/result/hhie-s");
    expect(tiles[0].className).toBe("journey-tile result-banner-mild_to_moderate pr-10");
    expect(lines(tiles[0])).toEqual([
      "您有一份還沒保存的結果",
      "2026/11/11・聽力對生活的影響",
      "14 分",
      "輕度到中度影響",
      "還留 5 天，看結果並保存",
      "›",
    ]);
    expect(tiles[0].lastElementChild.getAttribute("aria-hidden")).toBe("true");
    expect(root.textContent).not.toContain("您有 2 份");
  });

  it("with both, says 2 on top and stacks a tile each, the newest first", () => {
    saveGuestResult(guestResult());
    saveGuestResult(
      guestResult({
        code: "hhia-s",
        finishedAt: NOW - DAY / 24,
        total: 4,
        level: { code: "normal", text: "無／極輕微影響", color: "normal" },
      }),
    );
    show();
    expect(root.firstElementChild.tagName).toBe("P");
    expect(root.firstElementChild.textContent).toBe("您有 2 份還沒保存的結果");
    const tiles = [...root.querySelectorAll("a")];
    expect(tiles.map((tile) => tile.getAttribute("href"))).toEqual([
      "/guest/result/hhia-s",
      "/guest/result/hhie-s",
    ]);
    expect(tiles.map(lines)).toEqual([
      ["2026/11/13・聽力對生活的影響", "4 分", "無／極輕微影響", "還留 7 天，看結果並保存", "›"],
      ["2026/11/11・聽力對生活的影響", "14 分", "輕度到中度影響", "還留 5 天，看結果並保存", "›"],
    ]);
    expect(tiles[0].className).toBe("journey-tile result-banner-normal pr-10");
  });

  // #492 acceptance 19, the home's half (self-review P1): past 7 days it is not shown, and gone.
  it("shows no result past its 7 days and deletes it from this browser", () => {
    saveGuestResult(guestResult({ finishedAt: NOW - 7 * DAY - 1 }));
    show();
    expect(root.hidden).toBe(true);
    expect(root.children).toHaveLength(0);
    expect(localStorage.getItem("hearwell:guest-result:hhie-s")).toBeNull();
  });

  it("beside an expired one, shows only the one still kept", () => {
    saveGuestResult(guestResult({ finishedAt: NOW - 8 * DAY }));
    saveGuestResult(guestResult({ code: "hhia-s", finishedAt: NOW - DAY }));
    show();
    expect([...root.querySelectorAll("a")].map((tile) => tile.getAttribute("href"))).toEqual([
      "/guest/result/hhia-s",
    ]);
    expect(root.textContent).toContain("您有一份還沒保存的結果");
    expect(Object.keys(localStorage)).toEqual(["hearwell:guest-result:hhia-s"]);
  });

  it("drawn again, shows what is kept now", () => {
    saveGuestResult(guestResult());
    show();
    localStorage.clear();
    show();
    expect(root.hidden).toBe(true);
    expect(root.children).toHaveLength(0);
  });
});
