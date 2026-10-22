import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { act, cleanup, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Spec docs/specs/phase-05/phase5_answer_flash.md: the page hides the Django form before it is drawn,
// and the React entry hands the page back to the form when it cannot take over.

// Tests run from frontend/ (npm test --prefix frontend); jsdom gives import.meta.url a non-file scheme.
const TEMPLATE = resolve(process.cwd(), "../screening/templates/screening/screening.html");
// The only script without attributes on the answer page: the one that runs before the form.
const inlineScript = () => {
  const found = readFileSync(TEMPLATE, "utf-8").match(/<script>([\s\S]*?)<\/script>/);
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

function page() {
  document.body.innerHTML = `
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
