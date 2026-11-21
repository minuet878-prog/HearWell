import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { act, cleanup, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveDraft } from "./draft.js";

// Spec docs/specs/phase-05/phase5_answer_flash.md: the page hides the Django form before it is drawn,
// and the React entry hands the page back to the form when it cannot take over.

// Tests run from frontend/ (npm test --prefix frontend); jsdom gives import.meta.url a non-file scheme.
const TEMPLATE = resolve(process.cwd(), "../screening/templates/screening/screening.html");
// The only script without a src on the answer page, the one that runs before the form; it carries
// the Content-Security-Policy nonce only.
const inlineScript = () => {
  const found = readFileSync(TEMPLATE, "utf-8").match(/<script(?: nonce="[^"]*")?>([\s\S]*?)<\/script>/);
  if (!found) throw new Error("screening.html has no inline <script>");
  return found[1];
};

const QUESTIONNAIRE = {
  id: 1,
  code: "hhie-s",
  name: "HHIE-S",
  levels: [],
  wearing_question: "這次填答時，您有沒有戴助聽器？",
  questions: [{ id: 11, number: 1, text: "第1題的完整題目文字", choices: [{ value: 4, label: "常常" }] }],
};

const html = () => document.documentElement;
const status = () => document.getElementById("answer-loading");
const form = () => document.getElementById("answer-form");
const app = () => document.getElementById("answer-app");
const intro = () => document.getElementById("answer-intro");
// Spec #611 Q2: the reassurance under the count, and its second sentence, drawn hidden.
const FIRST = "這不是考試，沒有對錯。";
const SECOND = "答到一半離開，答案會留在這支手機，7 天內回來可以接著答。";
const reassure = () => document.querySelector("#answer-head .answer-reassure");
const secondSentence = () => reassure().querySelector("[data-draft-line]");

function page() {
  document.body.innerHTML = `
    <div id="answer-head">
      <div class="bird-dialogue"><div class="bird-bubble"><p class="bird-lead">慢慢來，不用急。</p><h1 class="bird-title">聽力對生活的影響</h1></div></div>
      <p class="answer-meta">HHIE-S・共 10 題・大約 3 分鐘</p>
      <p class="answer-reassure">${FIRST}<span data-draft-line hidden>${SECOND}</span></p>
      <p class="answer-guest-line">沒註冊時只計算、不儲存。<a href="/privacy">隱私權說明</a></p>
    </div>
    <div id="answer-intro"><p>本問卷的目的在幫助您了解自己的聽力。</p></div>
    <p id="answer-loading" role="status"></p>
    <div id="answer-app" data-questionnaire-id="1" data-user-id="7" data-minutes="3"></div>
    <form id="answer-form">
      <input type="hidden" name="csrfmiddlewaretoken" value="token">
      <input type="radio" name="form-0-score" value="4" aria-label="常常">
    </form>`;
}

// Runs the page's inline script the way the browser does: before the form is drawn.
const runInline = () => new Function(inlineScript())();

async function startReact() {
  await act(async () => {
    await import("./answer-main.jsx");
  });
}

function respondWith(response) {
  globalThis.fetch = vi.fn(() => Promise.resolve(response));
}
const ok = { ok: true, status: 200, json: () => Promise.resolve(QUESTIONNAIRE) };

beforeEach(() => {
  vi.resetModules();
  localStorage.clear();
  // A test that starts past the wearing step leaves its step in the history entry (#245).
  history.replaceState(null, "");
  html().className = "";
  page();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("inline script", () => {
  it("hides the form and says the questions are loading (acceptance 1, 8)", () => {
    vi.useFakeTimers();
    runInline();
    expect(html().classList.contains("answer-loading")).toBe(true);
    expect(status().textContent).toBe("題目載入中…");
    expect(status().getAttribute("role")).toBe("status");
  });

  it("gives the page back to the form after 5 seconds (acceptance 4)", () => {
    vi.useFakeTimers();
    runInline();
    vi.advanceTimersByTime(4999);
    expect(html().classList.contains("answer-loading")).toBe(true);
    vi.advanceTimersByTime(1);
    expect(html().classList.contains("answer-loading")).toBe(false);
    expect(status().textContent).toBe("");
  });
});

describe("React entry", () => {
  it("takes over when the questions arrive in time (acceptance 2)", async () => {
    runInline();
    respondWith(ok);
    await startReact();
    // The first page of the one-question-per-page flow is the hearing aid question.
    await waitFor(() => expect(app().textContent).toContain("這次填答時，您有沒有戴助聽器？"));
    expect(form().hidden).toBe(true);
    expect(html().classList.contains("answer-loading")).toBe(false);
    expect(status().textContent).toBe("");
  });

  it("moves the page's intro and minutes into React (#153)", async () => {
    runInline();
    respondWith(ok);
    await startReact();
    await waitFor(() => expect(app().textContent).toContain("這次填答時，您有沒有戴助聽器？"));
    expect(intro().hidden).toBe(true);
    // Folded under 這份問卷在問什麼？ (#463).
    expect(app().textContent).not.toContain("本問卷的目的在幫助您了解自己的聽力。");
    act(() => [...app().querySelectorAll("button")].find((b) => b.textContent === "這份問卷在問什麼？").click());
    expect(app().textContent).toContain("本問卷的目的在幫助您了解自己的聽力。");
    act(() => app().querySelector("input[type=radio]").click());
    act(() => [...app().querySelectorAll("button")].find((b) => b.textContent === "下一題").click());
    expect(app().textContent).toContain("第 1 題／共 1 題・還剩大約 3 分鐘");
  });

  it("starts on 沒戴 when the page says so, with the page's own hint (#154)", async () => {
    app().dataset.preselectUnaided = "";
    // The Django form's hint is the only copy of the sentence; React shows whatever it says.
    form().insertAdjacentHTML("afterbegin", '<p id="hearing-aid-hint">頁面上的說明句</p>');
    runInline();
    respondWith(ok);
    await startReact();
    await waitFor(() => expect(app().textContent).toContain("頁面上的說明句"));
    const unaided = [...app().querySelectorAll("label")].find((l) => l.textContent === "沒戴");
    expect(unaided.querySelector("input").checked).toBe(true);
    // The hidden form keeps its hint, so React's copy needs an id of its own.
    const ids = [...document.querySelectorAll("[id]")].map((el) => el.id);
    expect(ids.filter((id, i) => ids.indexOf(id) !== i)).toEqual([]);
  });

  it("hands IOI-HA's norm token over and skips the wearing step (#245)", async () => {
    app().dataset.skipWearing = "";
    app().dataset.normToken = "signed-token";
    runInline();
    globalThis.fetch = vi.fn((url, options = {}) =>
      Promise.resolve(options.method === "POST" ? { ok: false, status: 500 } : ok),
    );
    await startReact();
    await waitFor(() => expect(app().textContent).toContain("第1題的完整題目文字"));
    expect(app().textContent).not.toContain("這次填答時，您有沒有戴助聽器？");
    act(() => app().querySelector("input[type=radio]").click());
    act(() => [...app().querySelectorAll("button")].find((b) => b.textContent.includes("送出")).click());
    await waitFor(() => expect(fetch.mock.calls.some(([, o]) => o?.method === "POST")).toBe(true));
    const [, post] = fetch.mock.calls.find(([, o]) => o?.method === "POST");
    expect(JSON.parse(post.body).norm_token).toBe("signed-token");
  });

  it("hands IOI-HA's norm basis over for item 1, and the intro without it (#463)", async () => {
    app().dataset.skipWearing = "";
    intro().innerHTML = '<p>本量表適合已配戴助聽器的人。</p><section data-intro-norm><p>本次常模依據：HHIE-S。</p></section>';
    intro().insertAdjacentHTML("afterend", '<template id="answer-norm"><p>本次常模依據：HHIE-S。</p></template>');
    runInline();
    respondWith(ok);
    await startReact();
    await waitFor(() => expect(app().textContent).toContain("第1題的完整題目文字"));
    expect(app().querySelector(".answer-norm").textContent).toBe("本次常模依據：HHIE-S。");
    act(() => [...app().querySelectorAll("button")].find((b) => b.textContent === "這份問卷在問什麼？").click());
    const fold = document.getElementById("answer-intro-text");
    expect(fold.textContent).toBe("本量表適合已配戴助聽器的人。");
    // The page's own copy keeps its norm section, for the fold from item 2 on.
    expect(intro().querySelector("[data-intro-norm]")).not.toBeNull();
  });

  // Back to the first screen is AnswerApp.test.jsx's and e2e's: 上一題 goes through the history,
  // and this file's earlier pages are never unmounted, so their apps would hear it too.
  it("folds the page head away past the first screen (readability batch 1)", async () => {
    runInline();
    respondWith(ok);
    await startReact();
    const part = (selector) => document.querySelector(`#answer-head ${selector}`);
    const screenReaderOnly = (selector) => part(selector).classList.contains("visually-hidden");
    const button = (name) => [...app().querySelectorAll("button")].find((b) => b.textContent.includes(name));
    await waitFor(() => expect(app().textContent).toContain("這次填答時，您有沒有戴助聽器？"));
    // #749: the bird and its bubble, the title in it, go together.
    expect([screenReaderOnly(".bird-dialogue"), screenReaderOnly(".answer-meta"), part(".answer-guest-line").hidden]).toEqual([false, false, false]);
    act(() => app().querySelector("input[type=radio]").click());
    act(() => button("下一題").click());
    await waitFor(() => expect(app().textContent).toContain("第1題的完整題目文字"));
    expect([screenReaderOnly(".bird-dialogue"), screenReaderOnly(".answer-meta"), part(".answer-guest-line").hidden]).toEqual([true, true, true]);
  });

  it("says both sentences once React takes over and keeps a draft (#611 Q2, acceptance 61)", async () => {
    runInline();
    respondWith(ok);
    await startReact();
    await waitFor(() => expect(app().textContent).toContain("這次填答時，您有沒有戴助聽器？"));
    expect(reassure().hidden).toBe(false);
    expect(secondSentence().hidden).toBe(false);
    expect(reassure().textContent).toBe(FIRST + SECOND);
  });

  it("keeps to the first sentence when the form comes back (#611 Q2, acceptance 63)", async () => {
    runInline();
    respondWith({ ok: false, status: 500, json: () => Promise.resolve({}) });
    await startReact();
    await waitFor(() => expect(form().hidden).toBe(false));
    expect(reassure().hidden).toBe(false);
    expect(secondSentence().hidden).toBe(true);
  });

  it("keeps to the first sentence when React is too late (#611 Q2, acceptance 63)", async () => {
    vi.useFakeTimers();
    runInline();
    vi.advanceTimersByTime(5000);
    vi.useRealTimers();
    let arrive;
    globalThis.fetch = vi.fn(() => new Promise((resolve) => (arrive = resolve)));
    await startReact();
    await act(async () => arrive(ok));
    await act(async () => new Promise((resolve) => setTimeout(resolve, 0)));
    expect(form().hidden).toBe(false);
    expect(secondSentence().hidden).toBe(true);
  });

  it("takes the reassurance away, for screen readers too, past the first screen (#611 Q2, acceptance 64)", async () => {
    runInline();
    respondWith(ok);
    await startReact();
    await waitFor(() => expect(app().textContent).toContain("這次填答時，您有沒有戴助聽器？"));
    act(() => app().querySelector("input[type=radio]").click());
    act(() => [...app().querySelectorAll("button")].find((b) => b.textContent.includes("下一題")).click());
    await waitFor(() => expect(app().textContent).toContain("第1題的完整題目文字"));
    // hidden, not visually-hidden: nothing left to read out again on each question.
    expect(reassure().hidden).toBe(true);
  });

  it("says it with the question whether to carry on, then folds it (#611 Q2, acceptance 65)", async () => {
    saveDraft({ userId: 7, questionnaireId: 1, key: crypto.randomUUID(), wearing: false, answers: {}, step: 1, savedAt: Date.now() });
    runInline();
    respondWith(ok);
    await startReact();
    await waitFor(() => expect(app().textContent).toContain("您上次答到第 1 題，要接著答嗎？"));
    expect(reassure().hidden).toBe(false);
    expect(secondSentence().hidden).toBe(false);
    act(() => [...app().querySelectorAll("button")].find((b) => b.textContent === "接著答").click());
    await waitFor(() => expect(app().textContent).toContain("第1題的完整題目文字"));
    expect(reassure().hidden).toBe(true);
  });

  it("brings the form back at once when loading fails (acceptance 3)", async () => {
    runInline();
    respondWith({ ok: false, status: 500, json: () => Promise.resolve({}) });
    await startReact();
    await waitFor(() => expect(html().classList.contains("answer-loading")).toBe(false));
    expect(status().textContent).toBe("");
    expect(form().hidden).toBe(false);
    expect(intro().hidden).toBe(false);
    expect(app().textContent).toBe("");
  });

  it("brings the form back at once when the network is down (acceptance 3)", async () => {
    runInline();
    globalThis.fetch = vi.fn(() => Promise.reject(new Error("offline")));
    await startReact();
    await waitFor(() => expect(html().classList.contains("answer-loading")).toBe(false));
    expect(form().hidden).toBe(false);
  });

  it("stays out once the form is back, keeping what was picked (acceptance 5)", async () => {
    vi.useFakeTimers();
    runInline();
    vi.advanceTimersByTime(5000);
    vi.useRealTimers();
    form().querySelector("[type=radio]").checked = true;

    let arrive;
    globalThis.fetch = vi.fn(() => new Promise((resolve) => (arrive = resolve)));
    await startReact();
    await act(async () => arrive(ok));
    // Give React the chance to draw if it (wrongly) still took over.
    await act(async () => new Promise((resolve) => setTimeout(resolve, 0)));

    expect(form().hidden).toBe(false);
    expect(form().querySelector("[type=radio]").checked).toBe(true);
    expect(intro().hidden).toBe(false);
    expect(app().textContent).toBe("");
  });
});

// Implementation decision I3: the web form saves records (a guest sending it is asked to log in
// and loses the answers), so a guest is asked to register instead of getting the form back.
describe("guest", () => {
  const CANNOT_LOAD = "這個瀏覽器載不出免註冊作答，請註冊後再做。";
  const note = () => document.getElementById("answer-guest-fallback");

  // As screening.html draws it for a guest (test_guest.GuestFallbackTests checks the template).
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="answer-head">
        <h1>聽力對生活的影響</h1>
        <p class="answer-meta">HHIE-S・共 10 題・大約 3 分鐘</p>
        <p class="answer-reassure">${FIRST}</p>
        <p class="answer-guest-line">沒註冊時只計算、不儲存。<a href="/privacy">隱私權說明</a></p>
      </div>
      <div id="answer-intro"><p>本問卷的目的在幫助您了解自己的聽力。</p></div>
      <p id="answer-loading" role="status"></p>
      <div id="answer-guest-fallback" role="alert" hidden>
        <p>${CANNOT_LOAD}</p><a href="/register?next=%2Fquestionnaire%2F1">註冊新帳號</a>
      </div>
      <div id="answer-app" data-questionnaire-id="1" data-user-id="" data-minutes="3" data-guest
        data-questionnaire-code="hhie-s" data-register-url="/register?next=%2Fquestionnaire%2F1"></div>
      <form id="answer-form">
        <input type="hidden" name="csrfmiddlewaretoken" value="token">
        <input type="radio" name="form-0-score" value="4" aria-label="常常">
      </form>`;
  });

  it("asks to register, not the form, when React is not ready in 5 seconds", () => {
    vi.useFakeTimers();
    runInline();
    vi.advanceTimersByTime(4999);
    expect(note().hidden).toBe(true);
    vi.advanceTimersByTime(1);
    expect(note().hidden).toBe(false);
    expect(note().textContent).toContain(CANNOT_LOAD);
    expect(form().hidden).toBe(true);
    expect(status().textContent).toBe("");
  });

  it("asks to register, not the form, when loading fails", async () => {
    runInline();
    respondWith({ ok: false, status: 500, json: () => Promise.resolve({}) });
    await startReact();
    await waitFor(() => expect(html().classList.contains("answer-loading")).toBe(false));
    expect(note().hidden).toBe(false);
    expect(form().hidden).toBe(true);
    expect(status().textContent).toBe("");
  });

  it("stays out of the way when React takes over in time", async () => {
    runInline();
    respondWith(ok);
    await startReact();
    await waitFor(() => expect(app().textContent).toContain("這次填答時，您有沒有戴助聽器？"));
    expect(note().hidden).toBe(true);
    expect(form().hidden).toBe(true);
  });

  // #611 Q2 (acceptance 62): a guest keeps no draft, so React adds nothing to the first sentence.
  it("keeps a guest's reassurance to the first sentence, above the guest line", async () => {
    runInline();
    respondWith(ok);
    await startReact();
    await waitFor(() => expect(app().textContent).toContain("這次填答時，您有沒有戴助聽器？"));
    expect(reassure().hidden).toBe(false);
    expect(reassure().textContent).toBe(FIRST);
    expect(reassure().nextElementSibling.className).toBe("answer-guest-line");
  });

  // I4: the page's register link goes to React for a browser that cannot keep the result.
  it("hands the register link over for a browser that cannot keep the result", async () => {
    const refused = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("refused", "QuotaExceededError");
    });
    try {
      runInline();
      respondWith(ok);
      await startReact();
      await waitFor(() => expect(app().textContent).toContain("這個瀏覽器不能暫存結果"));
      expect(app().querySelector("a").getAttribute("href")).toBe("/register?next=%2Fquestionnaire%2F1");
      expect(form().hidden).toBe(true);
      expect(note().hidden).toBe(true);
      expect(html().classList.contains("answer-loading")).toBe(false);
    } finally {
      refused.mockRestore();
    }
  });
});
