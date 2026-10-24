import { afterEach, describe, expect, it, vi } from "vitest";

import { DRAFT_PREFIX, MAX_AGE_MS, clearAllDrafts, clearDraft, loadDraft, saveDraft } from "./draft.js";

const NOW = Date.parse("2026-10-16T10:00:00+08:00");
const QUESTION_IDS = [11, 12, 13];

function draft(overrides = {}) {
  return {
    userId: 7,
    questionnaireId: 1,
    key: "9b2f6a4e-1c3d-4e5f-8a9b-0c1d2e3f4a5b",
    wearing: false,
    answers: { 11: 4, 12: 0 },
    step: 3,
    savedAt: NOW,
    ...overrides,
  };
}

const load = (overrides = {}) =>
  loadDraft({ questionnaireId: 1, userId: 7, questionIds: QUESTION_IDS, now: NOW, ...overrides });

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("saveDraft / loadDraft", () => {
  it("returns what was saved", () => {
    saveDraft(draft());
    expect(load()).toEqual(draft());
  });

  it("keeps a score of 0 as an answer", () => {
    saveDraft(draft({ answers: { 11: 0, 12: 0, 13: 0 } }));
    expect(load().answers).toEqual({ 11: 0, 12: 0, 13: 0 });
  });

  it("returns null when nothing is saved", () => {
    expect(load()).toBeNull();
  });

  // #326 B4: the answer page shows 已儲存 only when the draft was really kept.
  it("tells whether the draft was kept", () => {
    expect(saveDraft(draft())).toBe(true);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    expect(saveDraft(draft())).toBe(false);
  });

  it("keeps HHIE-S and HHIA-S apart", () => {
    saveDraft(draft({ questionnaireId: 1, answers: { 11: 4 } }));
    saveDraft(draft({ questionnaireId: 2, answers: { 21: 2 }, step: 1 }));
    expect(load().answers).toEqual({ 11: 4 });
    expect(load({ questionnaireId: 2, questionIds: [21] }).answers).toEqual({ 21: 2 });
  });
});

describe("loadDraft throws away drafts it must not use", () => {
  it("drops a draft older than 7 days", () => {
    saveDraft(draft({ savedAt: NOW - MAX_AGE_MS - 1 }));
    expect(load()).toBeNull();
    expect(localStorage.length).toBe(0);
  });

  it("keeps a draft exactly 7 days old", () => {
    saveDraft(draft({ savedAt: NOW - MAX_AGE_MS }));
    expect(load()).not.toBeNull();
  });

  it("drops every draft of another account, not only this questionnaire's", () => {
    saveDraft(draft({ userId: 8, questionnaireId: 1 }));
    saveDraft(draft({ userId: 8, questionnaireId: 2 }));
    expect(load()).toBeNull();
    expect(localStorage.length).toBe(0);
  });

  it("leaves unrelated storage alone", () => {
    localStorage.setItem("something-else", "x");
    saveDraft(draft({ userId: 8 }));
    load();
    expect(localStorage.getItem("something-else")).toBe("x");
  });

  it.each([
    ["not JSON", "{oops"],
    ["not an object", "42"],
    ["a question of another questionnaire", JSON.stringify(draft({ answers: { 99: 4 } }))],
    ["a score that is not a number", JSON.stringify(draft({ answers: { 11: "4" } }))],
    ["a step past the last question", JSON.stringify(draft({ step: 4 }))],
    ["no receipt number", JSON.stringify(draft({ key: undefined }))],
    ["answers that are null", JSON.stringify(draft({ answers: null }))],
    ["no answers at all", JSON.stringify(draft({ answers: undefined }))],
    ["answers that are a list", JSON.stringify(draft({ answers: [4, 0] }))],
    ["a hearing aid answer that is not true/false/null", JSON.stringify(draft({ wearing: "yes" }))],
  ])("drops a draft with %s", (_, raw) => {
    localStorage.setItem(`${DRAFT_PREFIX}1`, raw);
    expect(load()).toBeNull();
    expect(localStorage.getItem(`${DRAFT_PREFIX}1`)).toBeNull();
  });
});

describe("clearing", () => {
  it("clearDraft removes only that questionnaire", () => {
    saveDraft(draft({ questionnaireId: 1 }));
    saveDraft(draft({ questionnaireId: 2 }));
    clearDraft(1);
    expect(load()).toBeNull();
    expect(load({ questionnaireId: 2 })).not.toBeNull();
  });

  it("clearAllDrafts removes every draft and nothing else", () => {
    localStorage.setItem("something-else", "x");
    saveDraft(draft({ questionnaireId: 1 }));
    saveDraft(draft({ questionnaireId: 2, userId: 8 }));
    clearAllDrafts();
    expect(localStorage.length).toBe(1);
    expect(localStorage.getItem("something-else")).toBe("x");
  });
});

describe("when the browser refuses storage (private mode)", () => {
  it("does not throw and just keeps nothing", () => {
    const refuse = () => {
      throw new DOMException("denied", "SecurityError");
    };
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(refuse);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(refuse);
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(refuse);
    expect(() => saveDraft(draft())).not.toThrow();
    expect(load()).toBeNull();
    expect(() => clearDraft(1)).not.toThrow();
    expect(() => clearAllDrafts()).not.toThrow();
  });
});
