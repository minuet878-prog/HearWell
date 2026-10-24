import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

// Spec #326 acceptance 18 (D5), ticket #332: the 顯示 button on the login and register pages.
// A plain static file (not a Vite entry), so the test runs it as the page does.
const SCRIPT = resolve(process.cwd(), "../screening/static/screening/password-toggle.js");

// The slash across the eye: only the 隱藏 icon draws it.
const SLASH = "M3 3l18 18";

const input = () => document.getElementById("id_password");
const button = () => document.querySelector(".password-toggle");
const icon = () => button().querySelector("svg");

describe("show password button", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <button type="button" class="password-toggle" aria-controls="id_password" aria-label="顯示密碼" data-label="密碼" hidden>顯示</button>
      <input id="id_password" type="password">`;
    new Function(readFileSync(SCRIPT, "utf-8"))();
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("shows 顯示 with an open eye that is not read out", () => {
    expect(button().hidden).toBe(false);
    expect(button().textContent).toBe("顯示");
    expect(button().getAttribute("aria-label")).toBe("顯示密碼");
    expect(icon().getAttribute("aria-hidden")).toBe("true");
    expect(icon().innerHTML).not.toContain(SLASH);
  });

  it("shows the password, then says 隱藏 with a slashed eye", () => {
    button().click();
    expect(input().type).toBe("text");
    expect(button().textContent).toBe("隱藏");
    expect(button().getAttribute("aria-label")).toBe("隱藏密碼");
    expect(icon().getAttribute("aria-hidden")).toBe("true");
    expect(icon().innerHTML).toContain(SLASH);
  });

  it("a second press hides it again with the open eye back", () => {
    button().click();
    button().click();
    expect(input().type).toBe("password");
    expect(button().textContent).toBe("顯示");
    expect(button().getAttribute("aria-label")).toBe("顯示密碼");
    expect(icon().innerHTML).not.toContain(SLASH);
  });
});
