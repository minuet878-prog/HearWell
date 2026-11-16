import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Spec #611 J2 (acceptance 1-8, 10), ticket #614: on 註冊, 用 LINE 取名稱 and 忘記密碼, an email
// whose part after the @ is one or two letters off a common one is asked about under the field.
// A plain static file (not a Vite entry), so the test runs it as the page does, on the page's
// own markup: the empty status area the server sends under the field.
const SCRIPT = resolve(process.cwd(), "../screening/static/screening/email-hint.js");

function page(value = "") {
  document.body.innerHTML = `
    <form>
      <div class="auth-field">
        <label for="id_email">電子郵件</label>
        <div class="auth-input"><input type="email" name="email" id="id_email" value="${value}"></div>
        <div id="id_email_hint" class="email-hint" role="status"></div>
      </div>
      <button type="submit">送出</button>
    </form>`;
  new Function(readFileSync(SCRIPT, "utf-8"))();
}

const input = () => document.getElementById("id_email");
const hint = () => document.getElementById("id_email_hint");
const button = () => hint().querySelector("button");
// What shows: the status area's words but the screen-reader-only ones.
const shown = () =>
  [...hint().childNodes]
    .filter((node) => !node.classList?.contains("visually-hidden"))
    .map((node) => node.textContent)
    .join("");

// Typing, then leaving the field.
function leave(value) {
  input().value = value;
  input().dispatchEvent(new Event("input", { bubbles: true }));
  input().dispatchEvent(new FocusEvent("blur"));
}

describe("email typo hint", () => {
  beforeEach(() => page());

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  // 1
  it("asks under the field once the field is left", () => {
    leave("wang@gmial.com");
    expect(shown()).toBe("您是不是要打 wang@gmail.com？按這裡改");
    expect(hint().querySelector("b").textContent).toBe("wang@gmail.com");
    expect(button().type).toBe("button");
    expect(button().textContent).toBe("按這裡改");
  });

  it("does not ask while typing", () => {
    input().value = "wang@gmial.com";
    input().dispatchEvent(new Event("input", { bubbles: true }));
    expect(hint().textContent).toBe("");
  });

  // 2, 10
  it("puts the suggestion in the field, goes, says so and gives the field back", () => {
    leave("wang@gmial.com");
    button().click();
    expect(input().value).toBe("wang@gmail.com");
    expect(button()).toBeNull();
    expect(shown()).toBe("");
    expect(hint().querySelector(".visually-hidden").textContent).toBe("已改成 wang@gmail.com");
    expect(document.activeElement).toBe(input());
  });

  it("drops the screen reader's words when the right email is left again", () => {
    leave("wang@gmial.com");
    button().click();
    input().dispatchEvent(new FocusEvent("blur"));
    expect(hint().textContent).toBe("");
  });

  // 3: the mockup's typos for each of the seven: one letter more, less, wrong, or two swapped.
  it.each([
    ["gmial.com", "gmail.com"],
    ["gmai.com", "gmail.com"],
    ["gamil.com", "gmail.com"],
    ["gmail.con", "gmail.com"],
    ["gmaill.com", "gmail.com"],
    ["gnail.com", "gmail.com"],
    ["yaho.com.tw", "yahoo.com.tw"],
    ["yahoo.con.tw", "yahoo.com.tw"],
    ["yahoo.com.t", "yahoo.com.tw"],
    ["yhaoo.com.tw", "yahoo.com.tw"],
    ["yaho.com", "yahoo.com"],
    ["yahooo.com", "yahoo.com"],
    ["yahoo.cm", "yahoo.com"],
    ["hotmial.com", "hotmail.com"],
    ["hotmai.com", "hotmail.com"],
    ["hotmail.co", "hotmail.com"],
    ["hotmaill.com", "hotmail.com"],
    ["outlok.com", "outlook.com"],
    ["outloook.com", "outlook.com"],
    ["outlook.con", "outlook.com"],
    ["iclould.com", "icloud.com"],
    ["icoud.com", "icloud.com"],
    ["icloud.con", "icloud.com"],
    ["msa.hient.net", "msa.hinet.net"],
    ["msa.hinet.ne", "msa.hinet.net"],
    ["mas.hinet.net", "msa.hinet.net"],
    // Not Yahoo elsewhere: tw with the letters swapped, or one letter wrong.
    ["yahoo.com.wt", "yahoo.com.tw"],
    ["yahoo.com.te", "yahoo.com.tw"],
    // Two letters off: two swaps, a swap and a wrong one, two missing.
    ["gmial.cmo", "gmail.com"],
    ["gmial.con", "gmail.com"],
    ["gml.com", "gmail.com"],
  ])("asks about %s as %s", (typed, meant) => {
    leave(`wang@${typed}`);
    expect(shown()).toBe(`您是不是要打 wang@${meant}？按這裡改`);
  });

  // 3: the same, three or more off, or someone's own domain.
  it.each([
    "gmail.com",
    "yahoo.com.tw",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "icloud.com",
    "msa.hinet.net",
    "GMAIL.COM",
    "Yahoo.Com.Tw",
    "gmali.cmo.tw",
    "gmailll.comm",
    "example.com",
    "ntu.edu.tw",
  ])("does not ask about %s", (domain) => {
    leave(`wang@${domain}`);
    expect(hint().textContent).toBe("");
  });

  it("asks whatever the letter case, suggesting the domain in small letters", () => {
    leave("Wang@GMIAL.COM");
    expect(shown()).toBe("您是不是要打 Wang@gmail.com？按這裡改");
  });

  // 2: only the part after the last @ changes.
  it("keeps everything before the last @ as typed", () => {
    leave('"chen@home"@yaho.com.tw');
    expect(hint().querySelector("b").textContent).toBe('"chen@home"@yahoo.com.tw');
  });

  it("does not ask without an @", () => {
    leave("gmial.com");
    expect(hint().textContent).toBe("");
  });

  // 4: real addresses that look like one of the seven.
  it.each([
    "ymail.com",
    "mail.com",
    "email.com",
    "yahoo.com.hk",
    "yahoo.com.sg",
    "yahoo.com.au",
    "yahoo.com.my",
    "yahoo.com.ph",
    "yahoo.com.vn",
    "yahoo.com.br",
    "yahoo.com.mx",
    "yahoo.com.ar",
    "YAHOO.COM.HK",
    "ms1.hinet.net",
    "ms12.hinet.net",
    "ms99.hinet.net",
  ])("does not ask about %s, which is real", (domain) => {
    leave(`wang@${domain}`);
    expect(hint().textContent).toBe("");
  });

  // 5
  it("never stops the form being sent", () => {
    leave("wang@gmial.com");
    const sending = new Event("submit", { cancelable: true });
    document.querySelector("form").dispatchEvent(sending);
    expect(sending.defaultPrevented).toBe(false);
    expect(input().value).toBe("wang@gmial.com");
  });

  // 6
  it("goes when the email is changed to one not like any", () => {
    leave("wang@gmial.com");
    leave("wang@ntu.edu.tw");
    expect(hint().textContent).toBe("");
  });

  it("asks about the new one when changed to another typo", () => {
    leave("wang@gmial.com");
    leave("wang@hotmial.com");
    expect(shown()).toBe("您是不是要打 wang@hotmail.com？按這裡改");
  });

  // Leaving the field again on the same typo does not say it again to screen readers.
  it("leaves the question as it is when the same typo is left again", () => {
    leave("wang@gmial.com");
    const asked = button();
    input().dispatchEvent(new FocusEvent("blur"));
    expect(button()).toBe(asked);
  });

  // 8
  it("says nothing about an empty field", () => {
    leave("");
    expect(hint().textContent).toBe("");
    leave("   ");
    expect(hint().textContent).toBe("");
  });

  // 7
  it("asks on arrival about a typo the server kept after a mistake elsewhere", () => {
    page("wang@gmial.com");
    expect(shown()).toBe("您是不是要打 wang@gmail.com？按這裡改");
  });

  it("says nothing on arrival about a right email", () => {
    page("wang@gmail.com");
    expect(hint().textContent).toBe("");
  });

  // 9
  it("sends nothing anywhere", () => {
    const fetch = vi.fn();
    const beacon = vi.fn();
    const request = vi.fn();
    vi.stubGlobal("fetch", fetch);
    vi.stubGlobal("XMLHttpRequest", request);
    navigator.sendBeacon = beacon;
    page("wang@gmial.com");
    leave("wang@hotmial.com");
    button().click();
    expect(fetch).not.toHaveBeenCalled();
    expect(request).not.toHaveBeenCalled();
    expect(beacon).not.toHaveBeenCalled();
    delete navigator.sendBeacon;
  });
});
