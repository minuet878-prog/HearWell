import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AnswerApp from "./AnswerApp.jsx";
import { DRAFT_PREFIX, saveDraft } from "./draft.js";

const CHOICES = [
  { value: 4, label: "常常" },
  { value: 2, label: "有時" },
  { value: 0, label: "從未" },
];
const QUESTIONS = Array.from({ length: 10 }, (_, i) => ({
  id: 11 + i,
  number: i + 1,
  text: `第${i + 1}題的完整題目文字`,
  choices: CHOICES,
}));
const QUESTIONNAIRE = {
  id: 1, code: "hhie-s", name: "HHIE-S", levels: [], wearing_question: "這次填答時，您有沒有戴助聽器？", questions: QUESTIONS,
};
const USER_ID = 7;
const DRAFT_KEY = `${DRAFT_PREFIX}1`;
const FAILED = "送出失敗，請再按一次送出";
const MINUTES = 3;
const INTRO = "<p>本問卷的目的在幫助您了解自己的聽力。</p><p>請圈選常常、有時或從未。</p>";

// POSTs answer from `posts` in order: {status, body}, or an Error for a network failure.
function mockApi(posts = [{ status: 201, body: { id: 99 } }], questionnaire = QUESTIONNAIRE) {
  const queue = [...posts];
  globalThis.fetch = vi.fn((url, options = {}) => {
    if (!options.method || options.method === "GET") {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(questionnaire) });
    }
    const next = queue.shift();
    if (next instanceof Error) return Promise.reject(next);
    return Promise.resolve({
      ok: next.status < 300,
      status: next.status,
      json: () => Promise.resolve(next.body ?? {}),
    });
  });
}

const postCalls = () => fetch.mock.calls.filter(([, options]) => options?.method === "POST");
const postBody = (index = 0) => JSON.parse(postCalls()[index][1].body);
const postHeaders = (index = 0) => postCalls()[index][1].headers;

let navigate;
let onReady;

async function renderApp(props = {}) {
  render(
    <AnswerApp
      questionnaireId={1} userId={USER_ID} csrfToken="csrf-token" minutes={MINUTES} introHtml={INTRO}
      onReady={onReady} navigate={navigate} {...props}
    />,
  );
  await waitFor(() => expect(onReady).toHaveBeenCalled());
}

// The fieldset legend holds the progress and the question text.
const legend = () => screen.getByRole("group").querySelector("legend").textContent;
const radio = (label) => screen.getByRole("radio", { name: label });
const choose = (label) => fireEvent.click(radio(label));
const next = () => fireEvent.click(screen.getByRole("button", { name: "下一題" }));
const submit = () => fireEvent.click(screen.getByRole("button", { name: /送出/ }));

// Hearing aid page, then every question with `label`, ending on the last question.
function answerAll(label = "常常", wearing = "沒戴") {
  choose(wearing);
  next();
  QUESTIONS.forEach((_, i) => {
    choose(label);
    if (i < QUESTIONS.length - 1) next();
  });
}

beforeEach(() => {
  navigate = vi.fn();
  onReady = vi.fn();
  history.replaceState(null, "");
  mockApi();
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("pages", () => {
  it("starts with the hearing aid question and tells the page it is ready", async () => {
    await renderApp();
    expect(fetch).toHaveBeenCalledWith("/api/questionnaires/1/", expect.anything());
    expect(onReady).toHaveBeenCalledTimes(1);
    expect(legend()).toMatch(/這次填答時，您有沒有戴助聽器？/);
    expect(screen.getAllByRole("radio").map((r) => r.labels[0].textContent)).toEqual(["有戴", "沒戴"]);
    expect(screen.queryByRole("button", { name: "上一題" })).toBeNull();
  });

  it("asks the wearing question the questionnaire's data gives (#212, THI)", async () => {
    mockApi(undefined, { ...QUESTIONNAIRE, code: "thi", name: "THI", wearing_question: "您現在有沒有配戴助聽器？" });
    await renderApp();
    expect(legend()).toBe("您現在有沒有配戴助聽器？");
    expect(screen.getAllByRole("radio").map((r) => r.labels[0].textContent)).toEqual(["有戴", "沒戴"]);
  });

  it("then shows one question per page with its full text and choices", async () => {
    await renderApp();
    choose("沒戴");
    next();
    QUESTIONS.forEach((question, i) => {
      expect(legend()).toMatch(new RegExp(`^第 ${i + 1} 題／共 10 題・還剩大約 \\d 分鐘${question.text}$`));
      expect(screen.getAllByRole("radio").map((r) => r.labels[0].textContent)).toEqual(["常常", "有時", "從未"]);
      choose("有時");
      if (i < QUESTIONS.length - 1) next();
    });
    expect(screen.queryByRole("button", { name: "下一題" })).toBeNull();
    expect(screen.getByRole("button", { name: "送出" }).disabled).toBe(false);
  });

  it("does not show the questions if they cannot be loaded, so the Django form stays", async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) }));
    const { container } = render(
      <AnswerApp questionnaireId={1} userId={USER_ID} csrfToken="t" onReady={onReady} navigate={navigate} />,
    );
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(onReady).not.toHaveBeenCalled();
    expect(container.innerHTML).toBe("");
  });

  it("never shows a score", async () => {
    await renderApp();
    answerAll("常常");
    expect(document.body.textContent).not.toMatch(/分數|總分|分項/);
  });
});

describe("progress (#153)", () => {
  // Segments of the bar above the question (the register steps' bar); answered ones are done.
  const segments = () => [...document.querySelectorAll(".step-progress-bar > .step-progress-segment")];
  const done = () => segments().filter((s) => s.classList.contains("is-done"));
  const progressText = () => document.querySelector(".question-progress").textContent;

  async function answerUpTo(number) {
    await renderApp();
    choose("沒戴");
    next();
    for (let n = 1; n <= number; n++) {
      choose("有時");
      if (n < number) next();
    }
  }

  it("on question 3 of 10 shows 10 segments, 3 answered, and the minutes left", async () => {
    await answerUpTo(3);
    expect(segments()).toHaveLength(10);
    expect(done()).toHaveLength(3);
    // 3 minutes × 8 of 10 questions left (this one included) = 2.4, rounded to 2.
    expect(progressText()).toBe("第 3 題／共 10 題・還剩大約 2 分鐘");
  });

  it("counts the whole time on question 1 and at least 1 minute on the last", async () => {
    await answerUpTo(1);
    expect(progressText()).toBe("第 1 題／共 10 題・還剩大約 3 分鐘");
    for (let n = 2; n <= 10; n++) {
      next();
      choose("有時");
    }
    // 3 × 1 / 10 = 0.3 would round to 0.
    expect(progressText()).toBe("第 10 題／共 10 題・還剩大約 1 分鐘");
    expect(done()).toHaveLength(10);
  });

  it("does not count the hearing aid question", async () => {
    await renderApp();
    expect(document.querySelector(".question-progress")).toBeNull();
    expect(segments()).toHaveLength(0);
    choose("有戴");
    next();
    expect(progressText()).toMatch(/^第 1 題／共 10 題/);
    expect(done()).toHaveLength(0);
  });

  it("only recolours on the next question: the same segments stay, nothing moves (ADR 0006)", async () => {
    await answerUpTo(2);
    const before = segments();
    next();
    choose("有時");
    expect(segments()).toEqual(before);
    segments().forEach((segment, i) => expect(segment).toBe(before[i]));
    expect(done()).toEqual(before.slice(0, 3));
    expect(segments().every((s) => !s.hasAttribute("style"))).toBe(true);
  });

  it("styles the bar with colour only: answered blue, no transition, animation or transform", () => {
    const css = readFileSync(resolve(process.cwd(), "src/site.css"), "utf-8").replace(/\/\*[\s\S]*?\*\//g, "");
    const rules = [...css.matchAll(/([^{}]*\.step-progress-(?:bar|segment)[^{}]*)\{([^}]*)\}/g)];
    expect(rules.map(([, selector]) => selector.trim())).toEqual([
      ".step-progress-bar",
      ".step-progress-segment",
      ".step-progress-segment.is-done",
    ]);
    expect(rules.at(-1)[2]).toMatch(/background-color:\s*var\(--color-primary\)/);
    rules.forEach(([, , body]) => expect(body).not.toMatch(/transition|animation|transform/));
  });
});

describe("questionnaire intro (#153)", () => {
  const introText = () => screen.queryByText("本問卷的目的在幫助您了解自己的聽力。");
  const toggle = () => screen.queryByRole("button", { name: "這份問卷在問什麼？" });

  it("shows the intro in full on the hearing aid question", async () => {
    await renderApp();
    expect(introText()).not.toBeNull();
    expect(screen.getByText("請圈選常常、有時或從未。")).not.toBeNull();
    expect(toggle()).toBeNull();
  });

  it("folds it from question 1 on, and 這份問卷在問什麼？ opens it", async () => {
    await renderApp();
    choose("沒戴");
    next();
    expect(introText()).toBeNull();
    expect(toggle().getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle());
    expect(toggle().getAttribute("aria-expanded")).toBe("true");
    expect(introText()).not.toBeNull();
    expect(document.getElementById(toggle().getAttribute("aria-controls")).contains(introText())).toBe(true);
    fireEvent.click(toggle());
    expect(introText()).toBeNull();
  });

  it("shows it in full again back on the hearing aid question", async () => {
    await renderApp();
    choose("沒戴");
    next();
    history.back();
    await waitFor(() => expect(legend()).toMatch(/有沒有戴助聽器/));
    expect(introText()).not.toBeNull();
    expect(toggle()).toBeNull();
  });
});

describe("autosave note (#153)", () => {
  // The ticket's own wording, chosen by the site owner (drafts actually stay in this browser, draft.js).
  const NOTE = "答案會自動存在這支手機，中途離開也沒關係，下次打開會問您要不要接著答。";

  it("tells the user on opening the page, and on every question", async () => {
    await renderApp();
    expect(screen.getByText(NOTE)).not.toBeNull();
    choose("沒戴");
    next();
    expect(screen.getByText(NOTE)).not.toBeNull();
  });
});

describe("catching up an unaided record (#154)", () => {
  const HINT = "請想沒戴助聽器時的情況來回答";
  // answer-main.jsx reads the hint from the Django form on the page.
  const PRESELECTED = { preselectUnaided: true, unaidedHint: HINT };
  const group = () => screen.getByRole("group");

  it("starts on 沒戴 with the hint, read with the question", async () => {
    await renderApp(PRESELECTED);
    expect(radio("沒戴").checked).toBe(true);
    expect(radio("有戴").checked).toBe(false);
    expect(screen.getByRole("button", { name: "下一題" }).disabled).toBe(false);
    expect(group().getAttribute("aria-describedby")).toBe("answer-hearing-aid-hint");
    expect(document.getElementById("answer-hearing-aid-hint").textContent).toBe(HINT);
  });

  it("shows the hint only while 沒戴 is chosen (site owner's choice 1.B)", async () => {
    await renderApp(PRESELECTED);
    choose("有戴");
    expect(screen.queryByText(HINT)).toBeNull();
    expect(group().hasAttribute("aria-describedby")).toBe(false);
    choose("沒戴");
    expect(document.getElementById("answer-hearing-aid-hint").textContent).toBe(HINT);
    expect(group().getAttribute("aria-describedby")).toBe("answer-hearing-aid-hint");
  });

  it("sends 有戴 when the user changes it", async () => {
    await renderApp(PRESELECTED);
    answerAll("常常", "有戴");
    submit();
    await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(postBody().wearing_hearing_aid).toBe(true);
  });

  it("chooses nothing and says nothing without it", async () => {
    await renderApp();
    expect(screen.getAllByRole("radio").some((r) => r.checked)).toBe(false);
    expect(group().hasAttribute("aria-describedby")).toBe(false);
    expect(screen.queryByText(HINT)).toBeNull();
  });

  it("is no unfinished answer by itself: opening and leaving asks nothing next time", async () => {
    await renderApp(PRESELECTED);
    expect(localStorage.getItem(DRAFT_KEY)).toBeNull();
  });

  it("gives way to the user's own draft; starting over starts on 沒戴 again", async () => {
    saveDraft({ userId: USER_ID, questionnaireId: 1, key: crypto.randomUUID(), wearing: true, answers: {}, step: 0, savedAt: Date.now() });
    await renderApp(PRESELECTED);
    fireEvent.click(screen.getByRole("button", { name: "接著答" }));
    expect(radio("有戴").checked).toBe(true);
    cleanup();
    await renderApp(PRESELECTED);
    fireEvent.click(screen.getByRole("button", { name: "重新開始" }));
    expect(radio("沒戴").checked).toBe(true);
  });
});

describe("next and previous", () => {
  it("keeps 下一題 disabled until a choice is made, then moves focus to the question", async () => {
    await renderApp();
    expect(screen.getByRole("button", { name: "下一題" }).disabled).toBe(true);
    choose("有戴");
    // A real click leaves focus on the button; the page change must move it to the question.
    screen.getByRole("button", { name: "下一題" }).focus();
    next();
    expect(legend()).toMatch(/^第 1 題／共 10 題/);
    expect(screen.getByRole("button", { name: "下一題" }).disabled).toBe(true);
    expect(document.activeElement.tagName).toBe("LEGEND");
  });

  it("moves focus to the question after the browser back button too", async () => {
    await renderApp();
    choose("沒戴");
    next();
    screen.getByRole("button", { name: "上一題" }).focus();
    history.back();
    await waitFor(() => expect(legend()).toMatch(/有沒有戴助聽器/));
    expect(document.activeElement.tagName).toBe("LEGEND");
  });

  it("does not move focus on first load, so the title and instructions are read first", async () => {
    await renderApp();
    expect(document.activeElement).toBe(document.body);
  });

  it("上一題 goes back with the answer kept", async () => {
    await renderApp();
    choose("沒戴");
    next();
    choose("從未");
    next();
    choose("常常");
    next();
    fireEvent.click(screen.getByRole("button", { name: "上一題" }));
    await waitFor(() => expect(legend()).toMatch(/^第 2 題/));
    expect(radio("常常").checked).toBe(true);
  });

  it("the browser back button is the previous question", async () => {
    await renderApp();
    choose("沒戴");
    next();
    choose("從未");
    next();
    history.back();
    await waitFor(() => expect(legend()).toMatch(/^第 1 題/));
    expect(radio("從未").checked).toBe(true);
    history.back();
    await waitFor(() => expect(legend()).toMatch(/有沒有戴助聽器/));
    expect(radio("沒戴").checked).toBe(true);
  });

  it("does not add a history entry for the first page, so back from it leaves", async () => {
    const before = history.length;
    await renderApp();
    expect(history.length).toBe(before);
  });
});

describe("submitting", () => {
  it("posts the answers with a receipt number and goes to the result page", async () => {
    await renderApp();
    answerAll("常常", "有戴");
    submit();
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/submission/99"));
    expect(postCalls()[0][0]).toBe("/api/submissions/");
    expect(postBody()).toEqual({
      questionnaire: 1,
      wearing_hearing_aid: true,
      answers: QUESTIONS.map((q) => ({ question: q.id, score: 4 })),
    });
    const headers = postHeaders();
    expect(headers["X-CSRFToken"]).toBe("csrf-token");
    expect(headers["Content-Type"]).toBe("application/json");
    expect(headers["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("treats 從未 (0) as an answer", async () => {
    await renderApp();
    answerAll("從未");
    submit();
    await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(postBody().answers.every((a) => a.score === 0)).toBe(true);
    expect(postBody().wearing_hearing_aid).toBe(false);
  });

  it("sends only once on a double click and shows 送出中…", async () => {
    let release;
    globalThis.fetch = vi.fn((url, options = {}) => {
      if (options.method !== "POST") {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(QUESTIONNAIRE) });
      }
      return new Promise((resolve) => {
        release = () => resolve({ ok: true, status: 201, json: () => Promise.resolve({ id: 99 }) });
      });
    });
    await renderApp();
    answerAll();
    const button = screen.getByRole("button", { name: "送出" });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(postCalls()).toHaveLength(1);
    expect(screen.getByRole("button", { name: "送出中…" }).disabled).toBe(true);
    // While sending, answers cannot change, not even after the browser back button.
    expect(screen.getByRole("button", { name: "上一題" }).disabled).toBe(true);
    expect(screen.getAllByRole("radio").every((r) => r.matches(":disabled"))).toBe(true);
    history.back();
    await waitFor(() => expect(legend()).toMatch(/^第 9 題/));
    expect(screen.getAllByRole("radio").every((r) => r.matches(":disabled"))).toBe(true);
    release();
    await waitFor(() => expect(navigate).toHaveBeenCalledTimes(1));
  });

  it("after a network failure, sending again reuses the receipt number", async () => {
    mockApi([new TypeError("Failed to fetch"), { status: 201, body: { id: 99 } }]);
    await renderApp();
    answerAll();
    submit();
    await screen.findByText(FAILED);
    expect(radio("常常").checked).toBe(true);
    submit();
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/submission/99"));
    expect(postHeaders(1)["Idempotency-Key"]).toBe(postHeaders(0)["Idempotency-Key"]);
  });

  it("shows the API's Chinese message on 400 and keeps the answers", async () => {
    mockApi([{ status: 400, body: { answers: ["有題目沒有作答"] } }]);
    await renderApp();
    answerAll();
    submit();
    await screen.findByText(/送出的資料有誤：有題目沒有作答/);
    expect(radio("常常").checked).toBe(true);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("asks to try again on 500", async () => {
    mockApi([{ status: 500 }]);
    await renderApp();
    answerAll();
    submit();
    await screen.findByText(FAILED);
    expect(radio("常常").checked).toBe(true);
  });

  it("on 403 says the login expired and links to login and back", async () => {
    mockApi([{ status: 403, body: { detail: "Authentication credentials were not provided." } }]);
    await renderApp();
    answerAll();
    submit();
    await screen.findByText("登入已經過期，請重新登入");
    expect(screen.getByRole("link", { name: "登入" }).getAttribute("href")).toBe("/login?next=%2Fquestionnaire%2F1");
    expect(localStorage.getItem(DRAFT_KEY)).not.toBeNull();
  });

  it("on 409 says it was already sent, links to the records and forgets the answers", async () => {
    mockApi([{ status: 409, body: { detail: "這個收據編號已經用過" } }]);
    await renderApp();
    answerAll();
    submit();
    await screen.findByText("這份作答之前已經送出過");
    expect(screen.getByRole("link", { name: "到我的紀錄看結果" }).getAttribute("href")).toBe("/my_hearing");
    expect(localStorage.getItem(DRAFT_KEY)).toBeNull();
    expect(postCalls()).toHaveLength(1);
    // Going back must not save the finished answers (with their used receipt number) again.
    const popped = new Promise((resolve) => window.addEventListener("popstate", resolve, { once: true }));
    history.back();
    await popped;
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(localStorage.getItem(DRAFT_KEY)).toBeNull();
  });

  it("does not save the answers again after a successful submit, even after going back", async () => {
    await renderApp();
    answerAll();
    submit();
    await waitFor(() => expect(navigate).toHaveBeenCalled());
    history.back();
    await waitFor(() => expect(legend()).toMatch(/^第 9 題/));
    expect(localStorage.getItem(DRAFT_KEY)).toBeNull();
  });

  it("discards a draft with an empty answer when no choice offers N/A (#100)", async () => {
    const answers = Object.fromEntries(QUESTIONS.map((q) => [q.id, q.number === 3 ? null : 4]));
    saveDraft({ userId: USER_ID, questionnaireId: 1, key: crypto.randomUUID(), wearing: false, answers, step: 10, savedAt: Date.now() });
    await renderApp();
    expect(screen.queryByRole("button", { name: "接著答" })).toBeNull();
  });

  it("does not send with a missing answer and goes to the first missing question", async () => {
    // Only reachable through a broken saved draft: question 3 has no answer.
    const answers = Object.fromEntries(QUESTIONS.filter((q) => q.number !== 3).map((q) => [q.id, 4]));
    saveDraft({ userId: USER_ID, questionnaireId: 1, key: crypto.randomUUID(), wearing: false, answers, step: 10, savedAt: Date.now() });
    await renderApp();
    fireEvent.click(screen.getByRole("button", { name: "接著答" }));
    submit();
    await screen.findByText("還有 1 題沒有回答");
    await waitFor(() => expect(legend()).toMatch(/^第 3 題/));
    expect(postCalls()).toHaveLength(0);
  });
});

describe("keeping unfinished answers", () => {
  async function answerUpToQuestion4() {
    await renderApp();
    choose("沒戴");
    next();
    for (const label of ["常常", "有時", "從未"]) {
      choose(label);
      next();
    }
  }

  // Like a real reload: the browser keeps the history entries, including the current one's state.
  async function reload() {
    cleanup();
    await renderApp();
  }

  it("asks to continue after a reload, and continuing restores every answer", async () => {
    await answerUpToQuestion4();
    await reload();
    screen.getByRole("heading", { name: "您上次答到第 4 題，要接著答嗎？" });
    fireEvent.click(screen.getByRole("button", { name: "接著答" }));
    expect(legend()).toMatch(/^第 4 題/);
    history.back();
    await waitFor(() => expect(legend()).toMatch(/^第 3 題/));
    expect(radio("從未").checked).toBe(true);
    for (const [n, label] of [[2, "有時"], [1, "常常"]]) {
      fireEvent.click(screen.getByRole("button", { name: "上一題" }));
      await waitFor(() => expect(legend()).toMatch(new RegExp(`^第 ${n} 題`)));
      expect(radio(label).checked).toBe(true);
    }
    fireEvent.click(screen.getByRole("button", { name: "上一題" }));
    await waitFor(() => expect(radio("沒戴").checked).toBe(true));
  });

  it("starting over clears the answers and uses a new receipt number", async () => {
    await answerUpToQuestion4();
    const oldKey = JSON.parse(localStorage.getItem(DRAFT_KEY)).key;
    await reload();
    fireEvent.click(screen.getByRole("button", { name: "重新開始" }));
    expect(legend()).toMatch(/有沒有戴助聽器/);
    expect(screen.getAllByRole("radio").some((r) => r.checked)).toBe(false);
    answerAll();
    submit();
    await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(postHeaders()["Idempotency-Key"]).not.toBe(oldKey);
  });

  it("does not ask again after a successful submit", async () => {
    await renderApp();
    answerAll();
    submit();
    await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(localStorage.getItem(DRAFT_KEY)).toBeNull();
    await reload();
    expect(screen.queryByRole("button", { name: "接著答" })).toBeNull();
    expect(legend()).toMatch(/有沒有戴助聽器/);
  });

  it("keeps the receipt number across a reload when the response was lost", async () => {
    mockApi([new TypeError("Failed to fetch"), { status: 200, body: { id: 99 } }]);
    await renderApp();
    answerAll();
    submit();
    await screen.findByText(FAILED);
    await reload();
    fireEvent.click(screen.getByRole("button", { name: "接著答" }));
    submit();
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/submission/99"));
    expect(postHeaders(1)["Idempotency-Key"]).toBe(postHeaders(0)["Idempotency-Key"]);
  });

  it("still works when the browser refuses storage", async () => {
    const refuse = () => {
      throw new DOMException("denied", "SecurityError");
    };
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(refuse);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(refuse);
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(refuse);
    await renderApp();
    answerAll();
    submit();
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/submission/99"));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("history after a reload (review F1)", () => {
  // An entry for the questionnaire list, then the answer page's own entry.
  function openFromList() {
    history.replaceState({ page: "list" }, "");
    history.pushState(null, "");
  }

  async function back() {
    const popped = new Promise((resolve) => window.addEventListener("popstate", resolve, { once: true }));
    history.back();
    await popped;
    await new Promise((resolve) => setTimeout(resolve, 0));
  }

  // Presses back until the questionnaire list; returns how many presses it took.
  async function backToList() {
    for (let presses = 1; presses <= 20; presses++) {
      await back();
      if (history.state?.page === "list") return presses;
    }
    return Infinity;
  }

  async function answerUpToQuestion3() {
    await renderApp();
    choose("沒戴");
    next();
    for (const label of ["常常", "有時"]) {
      choose(label);
      next();
    }
  }

  async function reload() {
    cleanup();
    await renderApp();
  }

  it("without a reload, question 3 is four presses from the list", async () => {
    openFromList();
    await answerUpToQuestion3();
    expect(await backToList()).toBe(4);
  });

  it("after a reload and continuing, question 3 is still four presses from the list", async () => {
    openFromList();
    await answerUpToQuestion3();
    await reload();
    fireEvent.click(screen.getByRole("button", { name: "接著答" }));
    expect(legend()).toMatch(/^第 3 題/);
    await back();
    expect(legend()).toMatch(/^第 2 題/);
    expect(radio("有時").checked).toBe(true);
    expect(await backToList()).toBe(3);
  });

  it("after a reload and starting over, the first page is one press from the list", async () => {
    openFromList();
    await answerUpToQuestion3();
    await reload();
    fireEvent.click(screen.getByRole("button", { name: "重新開始" }));
    await waitFor(() => expect(history.state).toEqual({ answerStep: 0 }));
    expect(legend()).toMatch(/有沒有戴助聽器/);
    expect(await backToList()).toBe(1);
  });

  it("coming back from the result page starts over one press from the list", async () => {
    openFromList();
    await renderApp();
    answerAll();
    submit();
    await waitFor(() => expect(navigate).toHaveBeenCalled());
    // The result page is its own entry; back from it reloads the answer page on step 10's entry.
    history.pushState({ page: "result" }, "");
    await back();
    await reload();
    await waitFor(() => expect(history.state).toEqual({ answerStep: 0 }));
    expect(legend()).toMatch(/有沒有戴助聽器/);
    expect(await backToList()).toBe(1);
  });
});


describe("SSQ12-TW", () => {
  const ssq = {
    ...QUESTIONNAIRE, code: "ssq12-tw", name: "SSQ12-TW",
    questions: QUESTIONS.map((q) => ({ ...q,
      choices: [...Array.from({ length: 11 }, (_, value) => ({ value, label: String(value) })), { value: null, label: "不適用" }],
      scale: { min_label: "完全不行", max_label: "輕鬆做到" },
    })),
  };

  it("does not answer by default and preserves explicit N/A and zero in drafts", async () => {
    mockApi(undefined, ssq);
    await renderApp();
    choose("沒戴");
    next();
    expect(screen.getByText("未作答")).toBeTruthy();
    expect(screen.getByRole("button", { name: "下一題" }).disabled).toBe(true);
    fireEvent.pointerUp(screen.getByRole("slider"));
    expect(screen.getByText("5 分")).toBeTruthy();
    choose("不適用");
    expect(screen.getByRole("button", { name: "下一題" }).disabled).toBe(false);
    next();
    fireEvent.change(screen.getByRole("slider"), { target: { value: "0" } });
    expect(screen.getByText("0 分")).toBeTruthy();
    const saved = JSON.parse(localStorage.getItem(DRAFT_KEY));
    expect(saved.answers[11]).toBe(null);
    expect(saved.answers[12]).toBe(0);
    cleanup();
    await renderApp();
    fireEvent.click(screen.getByRole("button", { name: "接著答" }));
    expect(screen.getByText("0 分")).toBeTruthy();
  });

  it("keeps N/A in drafts for any questionnaire whose choices offer it (#100)", async () => {
    mockApi(undefined, { ...ssq, code: "another-questionnaire" });
    await renderApp();
    choose("沒戴");
    next();
    choose("不適用");
    next();
    fireEvent.change(screen.getByRole("slider"), { target: { value: "0" } });
    cleanup();
    await renderApp();
    fireEvent.click(screen.getByRole("button", { name: "接著答" }));
    expect(screen.getByText("0 分")).toBeTruthy();
  });

  it("increments by one and sends explicit N/A without treating it as missing", async () => {
    mockApi(undefined, ssq);
    await renderApp();
    choose("有戴");
    next();
    fireEvent.change(screen.getByRole("slider"), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: "增加 1 分" }));
    expect(screen.getByText("7 分")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "減少 1 分" }));
    expect(screen.getByText("6 分")).toBeTruthy();
    for (let i = 0; i < QUESTIONS.length; i++) {
      choose("不適用");
      if (i < QUESTIONS.length - 1) next();
    }
    submit();
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/submission/99"));
    expect(postBody().answers.every((a) => a.score === null)).toBe(true);
  });
});

describe("always-aided (#170)", () => {
  // Same shape as SADL: 7 labelled choices, with 不適用 only on items 11 and 14.
  const SADL_LABELS = ["一點都沒有", "一點點", "有一些", "中等程度", "相當程度", "非常多", "極度"];
  const sadlChoices = (number) => {
    const choices = SADL_LABELS.map((label, i) => ({ value: i + 1, label }));
    return [11, 14].includes(number) ? [...choices, { value: null, label: "不適用" }] : choices;
  };
  const SADL_QUESTIONS = Array.from({ length: 15 }, (_, i) => {
    const number = i + 1;
    return { id: 200 + i, number, text: `SADL 第${number}題`, choices: sadlChoices(number) };
  });
  const SADL = { id: 2, code: "sadl", name: "SADL", levels: [], questions: SADL_QUESTIONS };

  function answerAllSadl(label = "一點都沒有") {
    SADL_QUESTIONS.forEach((_, i) => {
      choose(label);
      if (i < SADL_QUESTIONS.length - 1) next();
    });
  }

  it("starts directly on question 1, with no wearing step or 上一題 button", async () => {
    mockApi(undefined, SADL);
    await renderApp({ alwaysAided: true });
    expect(screen.queryByText("這次填答時，您有沒有戴助聽器？")).toBeNull();
    expect(legend()).toMatch(/^第 1 題／共 15 題・還剩大約 \d 分鐘SADL 第1題$/);
    expect(screen.queryByRole("button", { name: "上一題" })).toBeNull();
  });

  it("shows all seven labels on every item, and 不適用 only on items 11 and 14", async () => {
    mockApi(undefined, SADL);
    await renderApp({ alwaysAided: true });
    expect(screen.getAllByRole("radio").map((r) => r.labels[0].textContent)).toEqual(SADL_LABELS);
    for (let i = 0; i < 10; i++) {
      choose(SADL_LABELS[0]);
      next();
    }
    expect(legend()).toMatch(/第11題$/);
    expect(screen.getAllByRole("radio").map((r) => r.labels[0].textContent)).toEqual([
      ...SADL_LABELS,
      "不適用",
    ]);
    choose("不適用");
    next();
    expect(legend()).toMatch(/第12題$/);
    expect(screen.getAllByRole("radio").map((r) => r.labels[0].textContent)).toEqual(SADL_LABELS);
    choose(SADL_LABELS[0]);
    next();
    expect(legend()).toMatch(/第13題$/);
    choose(SADL_LABELS[0]);
    next();
    expect(legend()).toMatch(/第14題$/);
    expect(screen.getAllByRole("radio").map((r) => r.labels[0].textContent)).toEqual([
      ...SADL_LABELS,
      "不適用",
    ]);
  });

  it("sends wearing_hearing_aid true without ever asking", async () => {
    mockApi(undefined, SADL);
    await renderApp({ alwaysAided: true });
    answerAllSadl();
    submit();
    await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(postBody().wearing_hearing_aid).toBe(true);
  });

  it("keeps an unfinished answer and continues it from question 1, not a wearing step", async () => {
    mockApi(undefined, SADL);
    await renderApp({ alwaysAided: true });
    choose(SADL_LABELS[0]);
    next();
    choose(SADL_LABELS[1]);
    cleanup();
    await renderApp({ alwaysAided: true });
    screen.getByRole("heading", { name: "您上次答到第 2 題，要接著答嗎？" });
    fireEvent.click(screen.getByRole("button", { name: "接著答" }));
    expect(legend()).toMatch(/^第 2 題/);
    expect(radio(SADL_LABELS[1]).checked).toBe(true);
    history.back();
    await waitFor(() => expect(legend()).toMatch(/^第 1 題/));
    expect(radio(SADL_LABELS[0]).checked).toBe(true);
    expect(screen.queryByRole("button", { name: "上一題" })).toBeNull();
  });
});
