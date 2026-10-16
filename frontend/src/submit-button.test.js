import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Spec docs/specs/phase6_web_double_submit.md 4.2, acceptance 10-12: the web answer form's
// submit button. A plain static file (not a Vite entry), so the test runs it as the page does.
const SCRIPT = resolve(process.cwd(), "../screening/static/screening/submit-button.js");

const form = () => document.getElementById("answer-form");
const button = () => form().querySelector('[type="submit"]');
const status = () => document.getElementById("submit-status");

function page() {
  document.body.innerHTML = `
    <form id="answer-form">
      <input type="submit" value="送出">
    </form>
    <p id="submit-status" role="status"></p>`;
  new Function(readFileSync(SCRIPT, "utf-8"))();
}

const submit = () => form().dispatchEvent(new Event("submit", { cancelable: true }));

describe("submit button feedback", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    page();
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("starts as a normal button", () => {
    expect(button().disabled).toBe(false);
    expect(button().value).toBe("送出");
    expect(status().textContent).toBe("");
  });

  // 10
  it("shows it is sending and cannot be pressed again", () => {
    submit();
    expect(button().disabled).toBe(true);
    expect(button().value).toBe("送出中…");
    expect(status().textContent).toBe("送出中…");
  });

  // 11
  it("gives the button back after 10 seconds without an answer", () => {
    submit();
    vi.advanceTimersByTime(9999);
    expect(button().disabled).toBe(true);
    vi.advanceTimersByTime(1);
    expect(button().disabled).toBe(false);
    expect(button().value).toBe("送出");
    expect(status().textContent).toBe("");
  });

  // 12
  it("is a normal button again when the page comes back from the back button", () => {
    submit();
    window.dispatchEvent(new Event("pageshow"));
    expect(button().disabled).toBe(false);
    expect(button().value).toBe("送出");
    expect(status().textContent).toBe("");
    // The earlier 10-second timer must not fire into a later submit.
    submit();
    vi.advanceTimersByTime(9999);
    expect(button().disabled).toBe(true);
  });
});
