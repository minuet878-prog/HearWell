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
const QUESTIONNAIRE = { id: 1, code: "hhie-s", name: "HHIE-S", levels: [], questions: QUESTIONS };
const USER_ID = 7;
const DRAFT_KEY = `${DRAFT_PREFIX}1`;
const FAILED = "送出失敗，請再按一次送出";

// POSTs answer from `posts` in order: {status, body}, or an Error for a network failure.
function mockApi(posts = [{ status: 201, body: { id: 99 } }]) {
  const queue = [...posts];
  globalThis.fetch = vi.fn((url, options = {}) => {
    if (!options.method || options.method === "GET") {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(QUESTIONNAIRE) });
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

async function renderApp() {
  render(
    <AnswerApp questionnaireId={1} userId={USER_ID} csrfToken="csrf-token" onReady={onReady} navigate={navigate} />,
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

  it("then shows one question per page with its full text and choices", async () => {
    await renderApp();
    choose("沒戴");
    next();
    QUESTIONS.forEach((question, i) => {
      expect(legend()).toBe(`第 ${i + 1} 題／共 10 題${question.text}`);
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
