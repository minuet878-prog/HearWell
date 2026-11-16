import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

// Spec #326 acceptance 19 (D6), ticket #332: the register page's green ticks; spec #611 J4
// (ticket #615): the age under 出生年, there too on 用 LINE／Google 取名稱, which have no password.
// A plain static file (not a Vite entry), so the test runs it as the page does, on the page's
// own markup.
const SCRIPT = resolve(process.cwd(), "../screening/static/screening/register-checks.js");
const STATUS = '<p class="visually-hidden" role="status"></p>';

// With `wrong` ({field id: [Django error codes]}), the page as the server sends it back after
// mistakes in that field: Django's red frame (aria-invalid) and one line of error words per code
// (field_messages.html marks each with its code; "" for an error without one), which the field's
// aria-describedby points at.
function wrongAttrs(id, codes) {
  return codes
    ? `aria-invalid="true" aria-describedby="${id}_helptext ${id}_error"`
    : `aria-describedby="${id}_helptext"`;
}

function serverWords(id, codes) {
  if (!codes) return "";
  const lines = codes.map(
    (code) => `<p class="text-danger field-error"${code ? ` data-code="${code}"` : ""}>伺服器說錯了</p>`,
  );
  return `<div id="${id}_error">${lines.join("")}</div>`;
}

// `thisYear` is this 民國 year as the server gives it (115: 2026), `latestYear` the latest birth
// year it accepts; `passwords: false` is 用 LINE／Google 取名稱, with no password fields.
function page({ thisYear = "115", latestYear = "97", year = "", wrong = {}, passwords = true } = {}) {
  const password2 = "id_password2";
  const birthYear = "id_roc_birth_year";
  const passwordFields = `
    <div class="auth-field">
      <div class="auth-input"><input type="password" id="id_password1"></div>
    </div>
    <div class="auth-field">
      <div class="auth-input">
        <input type="password" id="${password2}" ${wrongAttrs(password2, wrong[password2])}>
      </div>
      ${STATUS}
      ${serverWords(password2, wrong[password2])}
      <div id="${password2}_helptext">請再輸入一次同樣的密碼。</div>
    </div>`;
  document.body.innerHTML = `
    ${passwords ? passwordFields : ""}
    <div class="auth-field">
      <div class="input-group">
        <span class="input-group-text">民國</span>
        <input type="text" id="${birthYear}" data-max="${latestYear}" data-this-year="${thisYear}"
          value="${year}" ${wrongAttrs(birthYear, wrong[birthYear])}>
        <span class="input-group-text">年</span>
      </div>
      <p class="birth-age" id="${birthYear}_age" aria-hidden="true"></p>
      ${STATUS}
      ${serverWords(birthYear, wrong[birthYear])}
      <div id="${birthYear}_helptext">選填。</div>
    </div>`;
  new Function(readFileSync(SCRIPT, "utf-8"))();
}

const field = (id) => document.getElementById(id).closest(".auth-field");
// The tick is drawn in the field by site.css (checked end to end); here, the field's state.
const tickShown = (id) => document.getElementById(id).classList.contains("is-right");
const status = (id) => field(id).querySelector('[role="status"]').textContent;
// The age shown under the 民國［　］年 row.
const age = () => document.getElementById("id_roc_birth_year_age").textContent;

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
    expect(age()).toBe("");
  });

  // The server's rule (RegisterForm.clean_roc_birth_year): a whole 民國 year from 1 to the
  // latest year the page gives, 97 here; with the tick, the age this 民國 year (115) less it.
  it.each([
    ["1", 114],
    ["44", 71],
    ["97", 18],
    [" 44 ", 71],
    ["044", 71],
    ["４４", 71],
  ])("ticks 出生年 %j", (value, years) => {
    type("id_roc_birth_year", value);
    expect(tickShown("id_roc_birth_year")).toBe(true);
    expect(status("id_roc_birth_year")).toBe(`格式正確，今年滿 ${years} 歲`);
    expect(age()).toBe(`今年滿 ${years} 歲`);
  });

  // Spec #611 acceptance 15: wrong or empty, no tick, no age and no words; the server says why
  // on sending.
  it.each(["", "0", "98", "1950", "abc", "4.5", "-1", "²", "1e1"])("no tick for 出生年 %j", (value) => {
    type("id_roc_birth_year", "44");
    type("id_roc_birth_year", value);
    expect(tickShown("id_roc_birth_year")).toBe(false);
    expect(status("id_roc_birth_year")).toBe("");
    expect(age()).toBe("");
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

// Spec #611 J4 (ticket #615): 今年滿 76 歲 under the 民國［　］年 row while the tick shows; this
// 民國 year is the server's (115 here), never the device's date.
describe("the age under 出生年", () => {
  beforeEach(() => page());

  afterEach(() => {
    document.body.innerHTML = "";
  });

  // Acceptance 13.
  it("shows 今年滿 76 歲 for 39", () => {
    type("id_roc_birth_year", "39");
    expect(tickShown("id_roc_birth_year")).toBe(true);
    expect(age()).toBe("今年滿 76 歲");
  });

  // Story 15: a digit short still has the tick, and an age that shows the mistake.
  it("shows 今年滿 112 歲 for 3", () => {
    type("id_roc_birth_year", "3");
    expect(age()).toBe("今年滿 112 歲");
  });

  // Acceptance 16.
  it.each(["３９", " 39 ", "　39　"])("reads %j as 39", (value) => {
    type("id_roc_birth_year", value);
    expect(tickShown("id_roc_birth_year")).toBe(true);
    expect(age()).toBe("今年滿 76 歲");
    expect(status("id_roc_birth_year")).toBe("格式正確，今年滿 76 歲");
  });

  // Acceptance 17.
  it("follows the year when it changes", () => {
    type("id_roc_birth_year", "39");
    type("id_roc_birth_year", "40");
    expect(age()).toBe("今年滿 75 歲");
    expect(status("id_roc_birth_year")).toBe("格式正確，今年滿 75 歲");
  });

  // Acceptance 18: a right year the server kept after a mistake elsewhere.
  it("is there when the page opens with a right year", () => {
    page({ year: "39" });
    expect(tickShown("id_roc_birth_year")).toBe(true);
    expect(age()).toBe("今年滿 76 歲");
    expect(status("id_roc_birth_year")).toBe("格式正確，今年滿 76 歲");
  });

  it("is not there when the page opens with a wrong year", () => {
    page({ year: "195" });
    expect(age()).toBe("");
  });

  // Acceptance 20: this year is the page's, as the account's age counts it.
  it("takes this year from the page", () => {
    page({ thisYear: "116", latestYear: "98" });
    type("id_roc_birth_year", "39");
    expect(age()).toBe("今年滿 77 歲");
  });

  // Acceptance 19: said once; typing on in a right field with the same age says nothing again.
  it("says it once while the age stays the same", () => {
    const words = field("id_roc_birth_year").querySelector('[role="status"]');
    const said = new MutationObserver(() => {});
    said.observe(words, { childList: true, characterData: true, subtree: true });
    type("id_roc_birth_year", "3");
    type("id_roc_birth_year", "39");
    expect(said.takeRecords()).not.toHaveLength(0);
    expect(words.textContent).toBe("格式正確，今年滿 76 歲");
    type("id_roc_birth_year", "039");
    type("id_roc_birth_year", " 39");
    expect(said.takeRecords()).toHaveLength(0);
    said.disconnect();
  });
});

// Spec #611 acceptance 14: 用 LINE／Google 取名稱 have 出生年 but no password.
describe("a page with no password", () => {
  beforeEach(() => page({ passwords: false }));

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("ticks 出生年 and shows the age", () => {
    type("id_roc_birth_year", "39");
    expect(tickShown("id_roc_birth_year")).toBe(true);
    expect(age()).toBe("今年滿 76 歲");
    expect(status("id_roc_birth_year")).toBe("格式正確，今年滿 76 歲");
    type("id_roc_birth_year", "");
    expect(tickShown("id_roc_birth_year")).toBe(false);
    expect(age()).toBe("");
  });

  it("checks a year already there when the page opens", () => {
    page({ passwords: false, year: "39" });
    expect(age()).toBe("今年滿 76 歲");
  });

  it("drops the server's red frame for 出生年 once it is right", () => {
    page({ passwords: false, wrong: { id_roc_birth_year: [""] } });
    type("id_roc_birth_year", "39");
    expect(document.getElementById("id_roc_birth_year").hasAttribute("aria-invalid")).toBe(false);
    expect(document.getElementById("id_roc_birth_year_error")).toBeNull();
  });
});

// Owner's call (2026-10-24, #326 self-review): once the tick shows, the field drops the red
// frame and the server's words for it; going wrong again does not bring them back.
describe("a field the server called wrong", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  const input = (id) => document.getElementById(id);
  const red = (id) => input(id).getAttribute("aria-invalid") === "true";
  const serverError = (id) => document.getElementById(`${id}_error`);

  const matchPasswords = () => {
    type("id_password1", "Fake-pass-2468");
    type("id_password2", "Fake-pass-2468");
  };

  // 出生年's one error has no code; 密碼確認 here only says the two passwords differ.
  it.each([
    ["id_roc_birth_year", "", () => type("id_roc_birth_year", "44"), () => type("id_roc_birth_year", "0")],
    ["id_password2", "password_mismatch", matchPasswords, () => type("id_password2", "Fake-pass-246")],
  ])("%s keeps the red frame until the tick shows, then drops it for good", (id, code, right, wrongAgain) => {
    page({ wrong: { [id]: [code] } });
    type(id, "0");
    expect(red(id)).toBe(true);
    expect(serverError(id)).not.toBeNull();

    right();
    expect(tickShown(id)).toBe(true);
    expect(red(id)).toBe(false);
    expect(serverError(id)).toBeNull();
    // The help words stay described; the gone error is no longer pointed at.
    expect(input(id).getAttribute("aria-describedby")).toBe(`${id}_helptext`);

    wrongAgain();
    expect(tickShown(id)).toBe(false);
    expect(red(id)).toBe(false);
    expect(serverError(id)).toBeNull();
  });

  // Owner's call (2026-10-24): the tick only answers "the two passwords differ"; what the
  // server said about the password itself (too short, too common...) stays, red frame and all.
  it("drops only the mismatch from 密碼確認, keeping the password's own errors and red frame", () => {
    page({ wrong: { id_password2: ["password_mismatch", "password_too_short", "password_too_common"] } });
    matchPasswords();
    expect(tickShown("id_password2")).toBe(true);
    const left = [...serverError("id_password2").querySelectorAll("p")].map((line) => line.dataset.code);
    expect(left).toEqual(["password_too_short", "password_too_common"]);
    expect(red("id_password2")).toBe(true);
    expect(input("id_password2").getAttribute("aria-describedby")).toBe(
      "id_password2_helptext id_password2_error",
    );
  });

  it("keeps the password's own errors when there was no mismatch to drop", () => {
    page({ wrong: { id_password2: ["password_entirely_numeric"] } });
    matchPasswords();
    expect(tickShown("id_password2")).toBe(true);
    expect(serverError("id_password2").textContent).toContain("伺服器說錯了");
    expect(red("id_password2")).toBe(true);
  });

  it("leaves the other field's red frame alone", () => {
    page({ wrong: { id_roc_birth_year: [""], id_password2: ["password_mismatch"] } });
    type("id_roc_birth_year", "44");
    expect(red("id_password2")).toBe(true);
    expect(serverError("id_password2")).not.toBeNull();
  });
});
