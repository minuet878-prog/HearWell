import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Readability batch 3 (the owner's C1 B): under a new password, how many characters are in and
// how many are still missing. A plain static file (not a Vite entry), so the test runs it as the
// page does.
const SCRIPT = resolve(process.cwd(), "../screening/static/screening/password-count.js");

const input = () => document.getElementById("id_password1");
const line = () => document.querySelector(".password-count");
const status = () => document.querySelector(".password-count-status");

function type(value) {
  input().value = value;
  input().dispatchEvent(new Event("input"));
}

describe("password character count", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    document.body.innerHTML = `
      <div class="auth-field">
        <input id="id_password1" type="password">
        <p class="password-count" data-for="id_password1" data-min="8" aria-hidden="true" hidden></p>
        <p class="visually-hidden password-count-status" role="status"></p>
      </div>`;
    new Function(readFileSync(SCRIPT, "utf-8"))();
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("says nothing before anything is typed", () => {
    expect(line().hidden).toBe(true);
    expect(status().textContent).toBe("");
  });

  it("counts what is typed and what is still missing", () => {
    type("abcde");
    expect(line().hidden).toBe(false);
    expect(line().textContent).toBe("已經輸入 5 個字，還差 3 個");
    expect(line().classList.contains("is-enough")).toBe(false);
  });

  it("ticks once there are enough", () => {
    type("abcdefgh");
    expect(line().textContent).toBe("✓ 已經輸入 8 個字");
    expect(line().classList.contains("is-enough")).toBe(true);
    type("abcdefghij");
    expect(line().textContent).toBe("✓ 已經輸入 10 個字");
  });

  it("counts characters as the server does, an emoji as one", () => {
    // Django's MinimumLengthValidator takes len() of the password: code points, not UTF-16 units.
    type("密碼😀😀");
    expect(line().textContent).toBe("已經輸入 4 個字，還差 4 個");
  });

  it("goes quiet again when the field is emptied", () => {
    type("abc");
    type("");
    expect(line().hidden).toBe(true);
  });

  it("tells screen readers once typing pauses, not at every key", () => {
    type("abc");
    type("abcd");
    expect(status().textContent).toBe("");
    vi.advanceTimersByTime(1000);
    expect(status().textContent).toBe("已經輸入 4 個字，還差 4 個");
  });

  it("counts a password the browser filled in before the script ran", () => {
    document.body.innerHTML = `
      <div class="auth-field">
        <input id="id_password1" type="password" value="abcdefgh">
        <p class="password-count" data-for="id_password1" data-min="8" aria-hidden="true" hidden></p>
        <p class="visually-hidden password-count-status" role="status"></p>
      </div>`;
    new Function(readFileSync(SCRIPT, "utf-8"))();
    expect(line().textContent).toBe("✓ 已經輸入 8 個字");
  });
});
