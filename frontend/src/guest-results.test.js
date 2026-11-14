import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DRAFT_PREFIX, loadDraft, saveDraft } from "./draft.js";
import {
  GUEST_PREFIX,
  MAX_AGE_MS,
  askAboutGuestResults,
  askToSaveGuestResults,
  canKeepGuestResults,
  clearGuestResult,
  loadGuestResult,
  saveGuestResult,
  saveGuestResults,
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

// The section's last row, as graded_result.html draws it for a guest (#498).
const CLEAR_ROW = `
  <details class="result-details" data-guest-clear="">
    <summary><span>清除這次結果</span></summary>
    <div>
      <p tabindex="-1" data-guest-clear-question="">清除後就找不回來了，確定嗎？</p>
      <button type="button" data-guest-clear-yes="">清除</button>
      <button type="button" data-guest-clear-no="">不要</button>
    </div>
  </details>`;

describe("showGuestResult (the guest result page)", () => {
  const SCORED = {
    questionnaire: { code: "hhie-s", name: "HHIE-S" },
    wearing_hearing_aid: false,
    wearing_text: "沒戴助聽器",
    scores: { total: 16, emotional: 12, social: 4 },
    level: { code: "mild_to_moderate", text: "輕度到中度影響", color: "mild_to_moderate" },
    html: `<div class="result-banner">總分 16 分</div>${CLEAR_ROW}`,
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

  // #492 acceptance 15, on the save card (the #493 mockup's D1): 2 days after, 5 days left.
  it("says on the save card how many days the result has left", async () => {
    const withCard = { ...SCORED, html: `<p>還留 <span data-guest-days-left></span> 天</p>${CLEAR_ROW}` };
    for (const [finishedAt, left] of [[NOW - 2 * DAY, "5"], [NOW, "7"], [NOW - 6.5 * DAY, "1"]]) {
      localStorage.clear();
      saveGuestResult(guestResult({ finishedAt }));
      await showGuestResult({ root, now: NOW, fetchScore: reply(200, withCard), navigate });
      expect(root.querySelector("[data-guest-days-left]").textContent).toBe(left);
    }
  });
});

// The save page (guest_save.html), #492 acceptance 22, 24, 25.
describe("saveGuestResults (the save page)", () => {
  const HHIA_S = guestResult({
    code: "hhia-s", questionnaireId: 3, answers: [{ question: 31, score: 2 }], wearing: true,
    key: "1f0e2d3c-4b5a-4968-8776-655443322110",
  });
  let root;
  let navigate;

  beforeEach(() => {
    document.body.innerHTML = `
      <div id="guest-save" data-submissions-url="/api/submissions/" data-done-url="/?from=save" data-home-url="/">
        <p data-guest-saving role="status" tabindex="-1">正在保存，請稍候。</p>
        <div data-guest-failed hidden>
          <div role="alert" tabindex="-1" data-guest-failed-list></div>
          <button type="button" data-guest-retry>再試一次</button>
        </div>
        <script id="guest-names" type="application/json">{"hhie-s": "聽力對生活的影響（HHIE-S）", "hhia-s": "聽力對生活的影響（HHIA-S）"}</script>
        <input type="hidden" name="csrfmiddlewaretoken" value="csrf-token">
      </div>`;
    root = document.getElementById("guest-save");
    navigate = vi.fn();
  });

  // Replies by questionnaire, so the order the two are sent in does not matter.
  const replies = (byId) => vi.fn((url, options) => {
    const status = byId[JSON.parse(options.body).questionnaire];
    return status instanceof Error
      ? Promise.reject(status)
      : Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve({}) });
  });

  it("sends each with its receipt number and the guest mark, as the answer page would", async () => {
    saveGuestResult(guestResult());
    const fetchSave = replies({ 1: 201 });
    await saveGuestResults({ root, now: NOW, fetchSave, navigate });
    expect(fetchSave).toHaveBeenCalledTimes(1);
    const [url, options] = fetchSave.mock.calls[0];
    expect(url).toBe("/api/submissions/");
    expect(options.method).toBe("POST");
    expect(options.headers["X-CSRFToken"]).toBe("csrf-token");
    expect(options.headers["Idempotency-Key"]).toBe(guestResult().key);
    expect(JSON.parse(options.body)).toEqual({
      questionnaire: 1,
      wearing_hearing_aid: false,
      answers: guestResult().answers,
      from_guest: true,
    });
  });

  it("saves both, clears them and goes home saying so", async () => {
    saveGuestResult(guestResult());
    saveGuestResult(HHIA_S);
    // 200: sent again, the record already there; saved all the same.
    const fetchSave = replies({ 1: 201, 3: 200 });
    await saveGuestResults({ root, now: NOW, fetchSave, navigate });
    expect(fetchSave).toHaveBeenCalledTimes(2);
    expect(loadGuestResult("hhie-s", NOW)).toBeNull();
    expect(loadGuestResult("hhia-s", NOW)).toBeNull();
    expect(navigate).toHaveBeenCalledWith("/?from=save");
  });

  it("keeps one not saved and says which, clearing the one saved", async () => {
    saveGuestResult(guestResult());
    saveGuestResult(HHIA_S);
    await saveGuestResults({ root, now: NOW, fetchSave: replies({ 1: 201, 3: 500 }), navigate });
    expect(loadGuestResult("hhie-s", NOW)).toBeNull();
    expect(loadGuestResult("hhia-s", NOW)).toEqual(HHIA_S);
    expect(navigate).not.toHaveBeenCalled();
    expect(root.querySelector("[data-guest-failed]").hidden).toBe(false);
    expect(root.querySelector("[data-guest-saving]").hidden).toBe(true);
    const list = root.querySelector("[data-guest-failed-list]").textContent;
    expect(list).toContain("「聽力對生活的影響（HHIA-S）」沒有存成");
    expect(list).not.toContain("HHIE-S");
  });

  it("keeps it after a network failure, and 再試一次 sends it again", async () => {
    vi.spyOn(Date, "now").mockReturnValue(NOW); // 再試一次 reads the clock again
    saveGuestResult(guestResult());
    const fetchSave = vi.fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce({ ok: true, status: 201, json: () => Promise.resolve({}) });
    await saveGuestResults({ root, now: NOW, fetchSave, navigate });
    expect(loadGuestResult("hhie-s", NOW)).toEqual(guestResult());
    expect(root.querySelector("[data-guest-failed-list]").textContent).toContain("「聽力對生活的影響（HHIE-S）」沒有存成");
    root.querySelector("[data-guest-retry]").click();
    await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith("/?from=save"));
    expect(fetchSave).toHaveBeenCalledTimes(2);
    // The same receipt number both times, so a lost reply cannot make two records.
    expect(fetchSave.mock.calls[1][1].headers["Idempotency-Key"]).toBe(guestResult().key);
    expect(loadGuestResult("hhie-s", NOW)).toBeNull();
  });

  // Self-review B2: a screen reader hears it is saving, then how it went.
  it("moves focus to the saving line while saving, and says when it is saved", async () => {
    saveGuestResult(guestResult());
    let reply;
    const fetchSave = vi.fn(() => new Promise((resolve) => { reply = resolve; }));
    const saving = saveGuestResults({ root, now: NOW, fetchSave, navigate });
    const line = root.querySelector("[data-guest-saving]");
    expect(document.activeElement).toBe(line);
    expect(line.textContent).toBe("正在保存，請稍候。");
    reply({ ok: true, status: 201, json: () => Promise.resolve({}) });
    await saving;
    expect(line.textContent).toBe("已保存，正在打開首頁。");
    expect(navigate).toHaveBeenCalledWith("/?from=save");
  });

  it("moves focus to what was not saved, and back to the saving line on 再試一次", async () => {
    saveGuestResult(guestResult());
    const fetchSave = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 500, json: () => Promise.resolve({}) })
      .mockReturnValueOnce(new Promise(() => {}));
    await saveGuestResults({ root, now: NOW, fetchSave, navigate });
    expect(document.activeElement).toBe(root.querySelector("[data-guest-failed-list]"));
    root.querySelector("[data-guest-retry]").click();
    expect(document.activeElement).toBe(root.querySelector("[data-guest-saving]"));
  });

  it("goes home when there is nothing to save", async () => {
    const fetchSave = replies({});
    await saveGuestResults({ root, now: NOW, fetchSave, navigate });
    expect(fetchSave).not.toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith("/");
  });
});

// #498 (#492 acceptance 16, 17; the #493 mockup's E1): the red row under the result opens its
// question; 不要 changes nothing, 清除 forgets only this questionnaire's result and goes home.
describe("清除這次結果 (the guest result page)", () => {
  const SCORED = { wearing_text: "沒戴助聽器", html: `<div class="result-banner">總分 16 分</div>${CLEAR_ROW}` };
  let root;
  let navigate;

  beforeEach(async () => {
    document.body.innerHTML = `
      <div id="guest-result" data-code="hhie-s" data-score-url="/api/guest-scores/" data-home-url="/">
        <div data-guest-shown hidden>
          <p>HHIE-S・<span data-guest-date></span> 作答・<span data-guest-wearing></span></p>
          <div data-guest-section></div>
        </div>
        <p role="alert" data-guest-error></p>
      </div>`;
    root = document.getElementById("guest-result");
    navigate = vi.fn();
    Element.prototype.scrollIntoView = vi.fn();
    saveGuestResult(guestResult());
    saveGuestResult(guestResult({ code: "hhia-s", questionnaireId: 3, total: 0 }));
    const fetchScore = vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(SCORED) }));
    await showGuestResult({ root, now: NOW, fetchScore, navigate });
  });

  afterEach(() => {
    delete Element.prototype.scrollIntoView;
  });

  const row = () => root.querySelector("[data-guest-clear]");
  const opened = async () => {
    const toggled = new Promise((resolve) => row().addEventListener("toggle", resolve, { once: true }));
    row().open = true;
    await toggled;
  };

  it("opens the question under the row, with focus on it and its buttons in view", async () => {
    await opened();
    expect(document.activeElement).toBe(root.querySelector("[data-guest-clear-question]"));
    expect(document.activeElement.textContent).toBe("清除後就找不回來了，確定嗎？");
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith({ block: "nearest" });
    expect(Element.prototype.scrollIntoView.mock.contexts[0]).toBe(root.querySelector("[data-guest-clear-no]"));
  });

  it("changes nothing on 不要: folded back, focus on the row, both results kept", async () => {
    await opened();
    root.querySelector("[data-guest-clear-no]").click();
    expect(row().open).toBe(false);
    expect(document.activeElement).toBe(row().querySelector("summary"));
    expect(loadGuestResult("hhie-s", NOW)).toEqual(guestResult());
    expect(loadGuestResult("hhia-s", NOW)).not.toBeNull();
    expect(root.querySelector("[data-guest-shown]").hidden).toBe(false);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("forgets only this questionnaire's on 清除 and goes home, the page emptied first", async () => {
    await opened();
    root.querySelector("[data-guest-clear-yes]").click();
    expect(loadGuestResult("hhie-s", NOW)).toBeNull();
    expect(localStorage.getItem(`${GUEST_PREFIX}hhie-s`)).toBeNull();
    expect(loadGuestResult("hhia-s", NOW)).toEqual(guestResult({ code: "hhia-s", questionnaireId: 3, total: 0 }));
    expect(navigate).toHaveBeenCalledWith("/");
    // Nothing of it left for the browser's cache of this page to show.
    expect(root.querySelector("[data-guest-shown]").hidden).toBe(true);
    expect(root.querySelector("[data-guest-section]").innerHTML).toBe("");
  });

  it("goes home again when the page comes back from the browser's cache after 清除", async () => {
    root.querySelector("[data-guest-clear-yes]").click();
    navigate.mockClear();
    const fetchScore = vi.fn();
    // What guest-result-main.js does on a pageshow from the cache.
    await showGuestResult({ root, now: NOW, fetchScore, navigate });
    expect(fetchScore).not.toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith("/");
    expect(root.querySelector("[data-guest-shown]").hidden).toBe(true);
  });
});

// #492 acceptance 19: 7 full days on, the guest result page shows none and the browser drops it.
describe("a guest result 7 days on (the guest result page)", () => {
  it("is not shown and is deleted from the browser", async () => {
    document.body.innerHTML = `
      <div id="guest-result" data-code="hhie-s" data-score-url="/api/guest-scores/" data-home-url="/">
        <div data-guest-shown hidden><div data-guest-section></div></div>
        <p role="alert" data-guest-error></p>
      </div>`;
    const root = document.getElementById("guest-result");
    saveGuestResult(guestResult());
    const fetchScore = vi.fn();
    const navigate = vi.fn();
    await showGuestResult({ root, now: NOW + 7 * DAY + 1, fetchScore, navigate });
    expect(fetchScore).not.toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith("/");
    expect(root.querySelector("[data-guest-shown]").hidden).toBe(true);
    expect(localStorage.getItem(`${GUEST_PREFIX}hhie-s`)).toBeNull();
  });
});

// #497 (#492 acceptance 26, 27): signed in by another way than the save card, any page
// (layout.html's guest-ask.js) takes a browser with guest results to the save page's question.
describe("askAboutGuestResults (every page signed in)", () => {
  it("goes to the question when a guest result is kept", () => {
    saveGuestResult(guestResult());
    const navigate = vi.fn();
    askAboutGuestResults({ askUrl: "/guest/save", now: NOW, navigate });
    expect(navigate).toHaveBeenCalledWith("/guest/save");
  });

  it("stays without one, or with only one 7 days old, which it drops", () => {
    const navigate = vi.fn();
    askAboutGuestResults({ askUrl: "/guest/save", now: NOW, navigate });
    saveGuestResult(guestResult());
    askAboutGuestResults({ askUrl: "/guest/save", now: NOW + 7 * DAY + 1, navigate });
    expect(navigate).not.toHaveBeenCalled();
    expect(localStorage.getItem(`${GUEST_PREFIX}hhie-s`)).toBeNull();
  });

  it("stays for an answer draft alone", () => {
    saveDraft(draft());
    const navigate = vi.fn();
    askAboutGuestResults({ askUrl: "/guest/save", now: NOW, navigate });
    expect(navigate).not.toHaveBeenCalled();
  });
});

// #497 (the #493 mockup's F2): the save page not come from the card. 要，存進這個帳號 saves as
// from the card; 不要，清掉這次結果 clears every guest result and saves none.
describe("askToSaveGuestResults (the save page's question)", () => {
  const HHIA_S = guestResult({
    code: "hhia-s", questionnaireId: 3, answers: [{ question: 31, score: 2 }], wearing: true,
    key: "1f0e2d3c-4b5a-4968-8776-655443322110", finishedAt: NOW + DAY, total: 6,
    level: { code: "normal", text: "無／極輕微影響", color: "normal" },
  });
  let root;
  let navigate;

  beforeEach(() => {
    document.body.innerHTML = `
      <div id="guest-save" data-submissions-url="/api/submissions/" data-done-url="/?from=save" data-home-url="/" data-asking>
        <h1>要把這次結果存到這個帳號嗎？</h1>
        <div data-guest-ask hidden>
          <p data-guest-ask-lead></p>
          <div data-guest-ask-list></div>
          <button type="button" data-guest-ask-yes>要，存進這個帳號</button>
          <button type="button" data-guest-ask-no>不要，清掉這次結果</button>
        </div>
        <p data-guest-saving role="status" tabindex="-1" hidden>正在保存，請稍候。</p>
        <div data-guest-failed hidden>
          <div role="alert" tabindex="-1" data-guest-failed-list></div>
          <button type="button" data-guest-retry>再試一次</button>
        </div>
        <script id="guest-names" type="application/json">{"hhie-s": "聽力對生活的影響（HHIE-S）", "hhia-s": "聽力對生活的影響（HHIA-S）"}</script>
        <script id="guest-topics" type="application/json">{"hhie-s": "聽力對生活的影響", "hhia-s": "聽力對生活的影響"}</script>
        <input type="hidden" name="csrfmiddlewaretoken" value="csrf-token">
      </div>`;
    root = document.getElementById("guest-save");
    navigate = vi.fn();
  });

  const created = () => vi.fn(() => Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({}) }));
  const tiles = () => [...root.querySelectorAll("[data-guest-ask-list] > *")];

  it("asks about one result, shown by its day, topic, score and level, saving nothing yet", () => {
    saveGuestResult(guestResult());
    const fetchSave = created();
    askToSaveGuestResults({ root, now: NOW, fetchSave, navigate });
    expect(root.querySelector("[data-guest-ask]").hidden).toBe(false);
    expect(root.querySelector("[data-guest-ask-lead]").textContent).toBe(
      "這支手機裡有一份還沒保存的結果。如果是幫家人做的，請選「不要」。",
    );
    expect(tiles()).toHaveLength(1);
    expect(tiles()[0].className).toContain("result-banner-mild_to_moderate");
    expect(tiles()[0].tagName).toBe("DIV"); // not a link: only to say which one it is
    expect(tiles()[0].textContent).toBe("2026/11/13・聽力對生活的影響16 分輕度到中度影響");
    expect(fetchSave).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
    expect(root.querySelector("[data-guest-saving]").hidden).toBe(true);
  });

  it("asks about two at once, each named with its questionnaire", () => {
    saveGuestResult(guestResult());
    saveGuestResult(HHIA_S);
    askToSaveGuestResults({ root, now: NOW + DAY, fetchSave: created(), navigate });
    expect(root.querySelector("[data-guest-ask-lead]").textContent).toBe(
      "這支手機裡有 2 份還沒保存的結果。如果是幫家人做的，請選「不要」。",
    );
    const texts = tiles().map((tile) => tile.textContent).sort();
    expect(texts).toEqual([
      "2026/11/13・聽力對生活的影響（HHIE-S）16 分・輕度到中度影響",
      "2026/11/14・聽力對生活的影響（HHIA-S）6 分・無／極輕微影響",
    ]);
  });

  it("要，存進這個帳號 saves them as from the save card and goes home saying so", async () => {
    saveGuestResult(guestResult());
    saveGuestResult(HHIA_S);
    const fetchSave = created();
    askToSaveGuestResults({ root, now: NOW + DAY, fetchSave, navigate });
    root.querySelector("[data-guest-ask-yes]").click();
    expect(root.querySelector("[data-guest-ask]").hidden).toBe(true);
    // Self-review B2: not left on the button just hidden.
    expect(document.activeElement).toBe(root.querySelector("[data-guest-saving]"));
    await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith("/?from=save"));
    expect(fetchSave).toHaveBeenCalledTimes(2);
    const keys = fetchSave.mock.calls.map(([, options]) => options.headers["Idempotency-Key"]).sort();
    expect(keys).toEqual([HHIA_S.key, guestResult().key].sort());
    for (const [, options] of fetchSave.mock.calls) expect(JSON.parse(options.body).from_guest).toBe(true);
    expect(loadGuestResult("hhie-s", NOW + DAY)).toBeNull();
    expect(loadGuestResult("hhia-s", NOW + DAY)).toBeNull();
  });

  it("不要，清掉這次結果 clears every guest result, saves none and goes home, the drafts kept", () => {
    saveGuestResult(guestResult());
    saveGuestResult(HHIA_S);
    saveDraft(draft());
    const fetchSave = created();
    askToSaveGuestResults({ root, now: NOW + DAY, fetchSave, navigate });
    root.querySelector("[data-guest-ask-no]").click();
    expect(fetchSave).not.toHaveBeenCalled();
    expect(Object.keys(localStorage).filter((key) => key.startsWith(GUEST_PREFIX))).toEqual([]);
    expect(navigate).toHaveBeenCalledWith("/");
    expect(localStorage.getItem(`${DRAFT_PREFIX}1`)).not.toBeNull();
  });

  it("goes home when there is nothing to ask about", () => {
    const fetchSave = created();
    askToSaveGuestResults({ root, now: NOW, fetchSave, navigate });
    expect(navigate).toHaveBeenCalledWith("/");
    expect(root.querySelector("[data-guest-ask]").hidden).toBe(true);
    expect(fetchSave).not.toHaveBeenCalled();
  });
});

// Implementation decision I4: checked before a guest starts answering, so nobody answers for a
// result the browser cannot keep (some private modes).
describe("canKeepGuestResults", () => {
  const refuse = () => {
    throw new DOMException("refused", "QuotaExceededError");
  };

  it("says yes when the browser keeps what is written, and leaves nothing behind", () => {
    expect(canKeepGuestResults()).toBe(true);
    expect(Object.keys(localStorage)).toEqual([]);
  });

  it("says no when writing throws", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(refuse);
    expect(canKeepGuestResults()).toBe(false);
  });

  it("says no when removing throws", () => {
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(refuse);
    expect(canKeepGuestResults()).toBe(false);
  });

  it("says no when the storage itself cannot be reached", () => {
    const blocked = vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    const kept = canKeepGuestResults();
    // Before afterEach clears the storage.
    blocked.mockRestore();
    expect(kept).toBe(false);
  });
});
