import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DRAFT_PREFIX, loadDraft, saveDraft } from "./draft.js";
import {
  GUEST_PREFIX,
  MAX_AGE_MS,
  clearGuestResult,
  loadGuestResult,
  saveGuestResult,
  showGuestResult,
} from "./guest-results.js";

const NOW = Date.parse("2026-11-13T10:00:00+08:00");
const DAY = 24 * 60 * 60 * 1000;

function guestResult(overrides = {}) {
  return {
    code: "hhie-s",
    questionnaireId: 1,
    answers: [{ question: 11, score: 4 }, { question: 12, score: 0 }],
    wearing: false,
    key: "9b2f6a4e-1c3d-4e5f-8a9b-0c1d2e3f4a5b",
    finishedAt: NOW,
    total: 16,
    level: { code: "mild_to_moderate", text: "輕度到中度影響", color: "mild_to_moderate" },
    ...overrides,
  };
}

function draft(overrides = {}) {
  return {
    userId: 7, questionnaireId: 1, key: "k", wearing: false, answers: { 11: 4 }, step: 2, savedAt: NOW,
    ...overrides,
  };
}
const loadTheDraft = () => loadDraft({ questionnaireId: 1, userId: 7, questionIds: [11, 12], now: NOW });

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("saveGuestResult / loadGuestResult", () => {
  it("returns what was saved, under the guest result's own key per questionnaire", () => {
    expect(saveGuestResult(guestResult())).toBe(true);
    expect(loadGuestResult("hhie-s", NOW)).toEqual(guestResult());
    expect(Object.keys(localStorage)).toEqual(["hearwell:guest-result:hhie-s"]);
    expect(GUEST_PREFIX).toBe("hearwell:guest-result:");
    expect(loadGuestResult("hhia-s", NOW)).toBeNull();
  });

  // #492 acceptance 18: the same questionnaire again keeps only the newest.
  it("keeps only the newest of the same questionnaire", () => {
    saveGuestResult(guestResult({ total: 16 }));
    saveGuestResult(guestResult({ total: 4, finishedAt: NOW + 1000, key: "another" }));
    expect(loadGuestResult("hhie-s", NOW + 1000)).toEqual(guestResult({ total: 4, finishedAt: NOW + 1000, key: "another" }));
    expect(Object.keys(localStorage).filter((key) => key.startsWith(GUEST_PREFIX))).toHaveLength(1);
  });

  it("keeps HHIE-S and HHIA-S apart", () => {
    saveGuestResult(guestResult());
    saveGuestResult(guestResult({ code: "hhia-s", questionnaireId: 3, total: 0 }));
    expect(loadGuestResult("hhie-s", NOW).total).toBe(16);
    expect(loadGuestResult("hhia-s", NOW).total).toBe(0);
  });

  it("keeps one for 7 days, then deletes it when any is read", () => {
    expect(MAX_AGE_MS).toBe(7 * DAY);
    saveGuestResult(guestResult());
    saveGuestResult(guestResult({ code: "hhia-s", finishedAt: NOW + DAY }));
    expect(loadGuestResult("hhie-s", NOW + 7 * DAY)).not.toBeNull();
    expect(loadGuestResult("hhia-s", NOW + 7 * DAY + 1)).not.toBeNull();
    expect(localStorage.getItem(`${GUEST_PREFIX}hhie-s`)).toBeNull();
    expect(loadGuestResult("hhie-s", NOW + 7 * DAY + 1)).toBeNull();
  });

  it("deletes a broken one", () => {
    localStorage.setItem(`${GUEST_PREFIX}hhie-s`, "{not json");
    localStorage.setItem(`${GUEST_PREFIX}hhia-s`, JSON.stringify({ code: "hhia-s" }));
    expect(loadGuestResult("hhie-s", NOW)).toBeNull();
    expect(loadGuestResult("hhia-s", NOW)).toBeNull();
    expect(Object.keys(localStorage)).toEqual([]);
  });

  it("keeps nothing and says so when the browser refuses storage", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    expect(saveGuestResult(guestResult())).toBe(false);
    expect(loadGuestResult("hhie-s", NOW)).toBeNull();
    expect(() => clearGuestResult("hhie-s")).not.toThrow();
  });
});

describe("clearGuestResult", () => {
  it("clears only that questionnaire's", () => {
    saveGuestResult(guestResult());
    saveGuestResult(guestResult({ code: "hhia-s" }));
    clearGuestResult("hhie-s");
    expect(loadGuestResult("hhie-s", NOW)).toBeNull();
    expect(loadGuestResult("hhia-s", NOW)).not.toBeNull();
  });
});

// #492 acceptance 20: reading, clearing or expiring one side leaves the other alone.
describe("beside the answer drafts", () => {
  it("does not touch a draft when a guest result is saved, read, cleared or expires", () => {
    saveDraft(draft());
    saveGuestResult(guestResult({ finishedAt: NOW - 8 * DAY }));
    expect(loadGuestResult("hhie-s", NOW)).toBeNull(); // expired, so deleted
    saveGuestResult(guestResult());
    loadGuestResult("hhie-s", NOW);
    clearGuestResult("hhie-s");
    expect(loadTheDraft()).toEqual(draft());
  });

  it("is not touched when a draft is read, expires or is another account's", () => {
    saveGuestResult(guestResult());
    saveDraft(draft({ savedAt: NOW - 8 * DAY }));
    saveDraft(draft({ questionnaireId: 2, userId: 8 }));
    expect(loadTheDraft()).toBeNull(); // the expired and the other account's drafts go
    expect(Object.keys(localStorage).filter((key) => key.startsWith(DRAFT_PREFIX))).toEqual([]);
    expect(loadGuestResult("hhie-s", NOW)).toEqual(guestResult());
  });
});

describe("showGuestResult (the guest result page)", () => {
  const SCORED = {
    questionnaire: { code: "hhie-s", name: "HHIE-S" },
    wearing_hearing_aid: false,
    wearing_text: "沒戴助聽器",
    scores: { total: 16, emotional: 12, social: 4 },
    level: { code: "mild_to_moderate", text: "輕度到中度影響", color: "mild_to_moderate" },
    html: '<div class="result-banner">總分 16 分</div>',
  };
  let root;
  let navigate;

  beforeEach(() => {
    document.body.innerHTML = `
      <div id="guest-result" data-code="hhie-s" data-score-url="/api/guest-scores/" data-home-url="/">
        <div data-guest-shown hidden>
          <p>HHIE-S・<span data-guest-date></span> 作答・<span data-guest-wearing></span></p>
          <div data-guest-section></div>
        </div>
        <p role="alert" data-guest-error></p>
        <input type="hidden" name="csrfmiddlewaretoken" value="csrf-token">
      </div>`;
    root = document.getElementById("guest-result");
    navigate = vi.fn();
  });

  const reply = (status, body) => vi.fn(() => Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body) }));

  it("has the kept answers scored again, not as just finished, and shows the section", async () => {
    saveGuestResult(guestResult());
    const fetchScore = reply(200, SCORED);
    await showGuestResult({ root, now: NOW, fetchScore, navigate });
    expect(fetchScore).toHaveBeenCalledTimes(1);
    const [url, options] = fetchScore.mock.calls[0];
    expect(url).toBe("/api/guest-scores/");
    expect(options.method).toBe("POST");
    expect(options.headers["X-CSRFToken"]).toBe("csrf-token");
    expect(JSON.parse(options.body)).toEqual({
      questionnaire: 1,
      wearing_hearing_aid: false,
      answers: guestResult().answers,
      just_finished: false,
    });
    expect(root.querySelector("[data-guest-section]").innerHTML).toBe(SCORED.html);
    expect(root.querySelector("[data-guest-date]").textContent).toBe("2026/11/13");
    expect(root.querySelector("[data-guest-wearing]").textContent).toBe("沒戴助聽器");
    expect(root.querySelector("[data-guest-shown]").hidden).toBe(false);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("goes home when there is none, or it expired", async () => {
    for (const finishedAt of [null, NOW - 8 * DAY]) {
      localStorage.clear();
      if (finishedAt) saveGuestResult(guestResult({ finishedAt }));
      const fetchScore = reply(200, SCORED);
      navigate.mockClear();
      await showGuestResult({ root, now: NOW, fetchScore, navigate });
      expect(navigate).toHaveBeenCalledWith("/");
      expect(fetchScore).not.toHaveBeenCalled();
      expect(root.querySelector("[data-guest-shown]").hidden).toBe(true);
    }
  });

  it("forgets one the server cannot score and goes home", async () => {
    saveGuestResult(guestResult());
    await showGuestResult({ root, now: NOW, fetchScore: reply(400, { answers: ["有題目沒有作答"] }), navigate });
    expect(navigate).toHaveBeenCalledWith("/");
    expect(loadGuestResult("hhie-s", NOW)).toBeNull();
  });

  it("says the server's words on 429, keeping the result", async () => {
    saveGuestResult(guestResult());
    const limit = "剛才做了很多次，請過一小時再試。您的作答沒有不見。";
    await showGuestResult({ root, now: NOW, fetchScore: reply(429, { detail: limit }), navigate });
    expect(root.querySelector("[data-guest-error]").textContent).toBe(limit);
    expect(root.querySelector("[data-guest-shown]").hidden).toBe(true);
    expect(loadGuestResult("hhie-s", NOW)).toEqual(guestResult());
    expect(navigate).not.toHaveBeenCalled();
  });

  it("asks to reload after a network failure, keeping the result", async () => {
    saveGuestResult(guestResult());
    const fetchScore = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    await showGuestResult({ root, now: NOW, fetchScore, navigate });
    expect(root.querySelector("[data-guest-error]").textContent).toBe("結果載入失敗，請重新整理這一頁");
    expect(loadGuestResult("hhie-s", NOW)).toEqual(guestResult());
  });
});
