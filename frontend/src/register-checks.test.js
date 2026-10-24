import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

// Spec #326 acceptance 19 (D6), ticket #332: the register page's green ticks. A plain static
// file (not a Vite entry), so the test runs it as the page does, on the page's own markup.
const SCRIPT = resolve(process.cwd(), "../screening/static/screening/register-checks.js");
const STATUS = '<p class="visually-hidden" role="status"></p>';

function page({ latestYear = "97", year = "" } = {}) {
  document.body.innerHTML = `
    <div class="auth-field">
      <div class="auth-input"><input type="password" id="id_password1"></div>
    </div>
    <div class="auth-field">
      <div class="auth-input"><input type="password" id="id_password2"></div>
      ${STATUS}
    </div>
    <div class="auth-field">
      <div class="input-group">
        <span class="input-group-text">民國</span>
        <input type="text" id="id_roc_birth_year" data-max="${latestYear}" value="${year}">
        <span class="input-group-text">年</span>
      </div>
      ${STATUS}
    </div>`;
  new Function(readFileSync(SCRIPT, "utf-8"))();
}

const field = (id) => document.getElementById(id).closest(".auth-field");
// The tick is drawn in the field by site.css (checked end to end); here, the field's state.
const tickShown = (id) => document.getElementById(id).classList.contains("is-right");
const status = (id) => field(id).querySelector('[role="status"]').textContent;

function type(id, value) {
  const input = document.getElementById(id);
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

describe("register field ticks", () => {
  beforeEach(() => page());

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("starts with no ticks and nothing said", () => {
    expect(tickShown("id_roc_birth_year")).toBe(false);
    expect(tickShown("id_password2")).toBe(false);
    expect(status("id_roc_birth_year")).toBe("");
    expect(status("id_password2")).toBe("");
  });

  // The server's rule (RegisterForm.clean_roc_birth_year): a whole 民國 year from 1 to the
  // latest year the page gives, 97 here.
  it.each(["1", "44", "97", " 44 ", "044", "４４"])("ticks 出生年 %j", (value) => {
    type("id_roc_birth_year", value);
    expect(tickShown("id_roc_birth_year")).toBe(true);
    expect(status("id_roc_birth_year")).toBe("格式正確");
  });

  it.each(["", "0", "98", "abc", "4.5", "-1", "²", "1e1"])("no tick for 出生年 %j", (value) => {
    type("id_roc_birth_year", "44");
    type("id_roc_birth_year", value);
    expect(tickShown("id_roc_birth_year")).toBe(false);
    expect(status("id_roc_birth_year")).toBe("");
  });

  it("takes the latest year from the page", () => {
    page({ latestYear: "98" });
    type("id_roc_birth_year", "98");
    expect(tickShown("id_roc_birth_year")).toBe(true);
  });

  it("ticks 密碼確認 once it matches 密碼", () => {
    type("id_password1", "Fake-pass-2468");
    type("id_password2", "Fake-pass-246");
    expect(tickShown("id_password2")).toBe(false);
    expect(status("id_password2")).toBe("");
    type("id_password2", "Fake-pass-2468");
    expect(tickShown("id_password2")).toBe(true);
    expect(status("id_password2")).toBe("兩次密碼相同");
  });

  it("takes the tick away when 密碼 changes after", () => {
    type("id_password1", "Fake-pass-2468");
    type("id_password2", "Fake-pass-2468");
    type("id_password1", "Fake-pass-24689");
    expect(tickShown("id_password2")).toBe(false);
    expect(status("id_password2")).toBe("");
  });

  it("gives no tick when both are empty", () => {
    type("id_password1", "");
    type("id_password2", "");
    expect(tickShown("id_password2")).toBe(false);
  });

  it("never ticks 密碼 itself", () => {
    type("id_password1", "Fake-pass-2468");
    type("id_password2", "Fake-pass-2468");
    expect(tickShown("id_password1")).toBe(false);
    expect(field("id_password1").querySelector('[role="status"]')).toBeNull();
  });

  // A value the server kept after an error elsewhere on the form is checked on arrival.
  it("ticks a right 出生年 already in the field when the page opens", () => {
    page({ year: "44" });
    expect(tickShown("id_roc_birth_year")).toBe(true);
  });
});
