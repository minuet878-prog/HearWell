import { afterEach, expect, it, vi } from "vitest";

import { DRAFT_PREFIX, MAX_AGE_MS, saveDraft } from "./draft.js";
import { showContinueNotice } from "./continue-notice.js";

// #326 E7 (#337): the home and screening pages, as continue_notice.html renders them for user 7.
const NOW = Date.parse("2026-10-24T10:00:00+08:00");
const QUESTIONNAIRES = [
  { id: 1, name: "聽力對生活的影響（HHIE-S）", url: "/questionnaire/1", questionIds: [11, 12, 13], allowNotApplicable: false },
  { id: 2, name: "日常聆聽能力（SSQ12-TW）", url: "/questionnaire/2", questionIds: [21, 22], allowNotApplicable: true },
];

function page() {
  const data = JSON.stringify({ userId: 7, questionnaires: QUESTIONNAIRES });
  document.body.innerHTML = `
    <script id="continue-notice-data" type="application/json">${data}</script>
    <div id="continue-notice"></div>`;
}

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

const lines = () => [...document.querySelectorAll("#continue-notice p")];
const texts = () => lines().map((line) => line.textContent);
const links = () => [...document.querySelectorAll("#continue-notice a")].map((a) => [a.textContent, a.getAttribute("href")]);

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.resetModules();
  document.body.innerHTML = "";
});

it("tells where this account's draft stopped and links to its questionnaire", () => {
  page();
  saveDraft(draft());
  showContinueNotice({ now: NOW });
  expect(texts()).toEqual(["您上次的「聽力對生活的影響（HHIE-S）」答到第 3 題，答案都還在。接著答"]);
  expect(links()).toEqual([["接著答", "/questionnaire/1"]]);
});

it("says 還沒答完 before item 1, as the answer page does", () => {
  page();
  saveDraft(draft({ step: 0, answers: {} }));
  showContinueNotice({ now: NOW });
  expect(texts()).toEqual(["您上次的「聽力對生活的影響（HHIE-S）」還沒答完，答案都還在。接著答"]);
});

it("gives each draft its own line, in the page's order", () => {
  page();
  saveDraft(draft({ questionnaireId: 2, answers: { 21: null }, step: 1 }));
  saveDraft(draft());
  showContinueNotice({ now: NOW });
  expect(texts()).toEqual([
    "您上次的「聽力對生活的影響（HHIE-S）」答到第 3 題，答案都還在。接著答",
    "您上次的「日常聆聽能力（SSQ12-TW）」答到第 1 題，答案都還在。接著答",
  ]);
  expect(links()).toEqual([
    ["接著答", "/questionnaire/1"],
    ["接著答", "/questionnaire/2"],
  ]);
});

it("shows nothing without a draft", () => {
  page();
  showContinueNotice({ now: NOW });
  expect(lines()).toEqual([]);
});

it("shows nothing of another account's draft, and leaves it to the answer page", () => {
  page();
  saveDraft(draft({ userId: 8 }));
  showContinueNotice({ now: NOW });
  expect(lines()).toEqual([]);
  expect(localStorage.getItem(`${DRAFT_PREFIX}1`)).not.toBeNull();
});

it("shows nothing of a draft over 7 days old", () => {
  page();
  saveDraft(draft({ savedAt: NOW - MAX_AGE_MS - 1 }));
  showContinueNotice({ now: NOW });
  expect(lines()).toEqual([]);
});

it("still shows a draft exactly 7 days old, which the answer page still offers", () => {
  page();
  saveDraft(draft({ savedAt: NOW - MAX_AGE_MS }));
  showContinueNotice({ now: NOW });
  expect(lines()).toHaveLength(1);
});

it("shows nothing of a draft the answer page could not resume", () => {
  page();
  saveDraft(draft({ answers: { 99: 4 } }));
  showContinueNotice({ now: NOW });
  expect(lines()).toEqual([]);
});

it("shows nothing, without an error, when the browser refuses storage", () => {
  page();
  saveDraft(draft());
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new DOMException("denied", "SecurityError");
  });
  expect(() => showContinueNotice({ now: NOW })).not.toThrow();
  expect(lines()).toEqual([]);
});

it("runs on its own when the page loads it", async () => {
  page();
  saveDraft(draft({ savedAt: Date.now() }));
  await import("./continue-notice-main.js");
  expect(links()).toEqual([["接著答", "/questionnaire/1"]]);
});
