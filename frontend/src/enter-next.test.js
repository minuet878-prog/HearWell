import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

// Spec #611 N3 (acceptance 22-27, 29, 30), ticket #616: in a form with several text fields, each
// one but the last says 下一個 on the phone keyboard and Enter there moves to the next one.
// A plain static file (not a Vite entry), so the test runs it as the page does.
const SCRIPT = resolve(process.cwd(), "../screening/static/screening/enter-next.js");

const run = () => new Function(readFileSync(SCRIPT, "utf-8"))();

// The register page's fields in its order, with what sits between them: the hidden next, the
// 顯示 buttons, the email typo question's button.
const REGISTER = `
  <form id="logout-form" method="post"><button type="submit">登出</button></form>
  <form method="post">
    <input type="hidden" name="next" value="/">
    <input type="text" name="username" id="id_username">
    <input type="email" name="email" id="id_email">
    <div id="id_email_hint" role="status"><button type="button">按這裡改</button></div>
    <button type="button" class="password-toggle" aria-controls="id_password1">顯示</button>
    <input type="password" name="password1" id="id_password1">
    <button type="button" class="password-toggle" aria-controls="id_password2">顯示</button>
    <input type="password" name="password2" id="id_password2">
    <input type="text" name="roc_birth_year" id="id_roc_birth_year" inputmode="numeric">
    <button type="submit">註冊</button>
  </form>`;

function page(html) {
  document.body.innerHTML = html;
  run();
}

const field = (id) => document.getElementById(id);
const hint = (element) => element.getAttribute("enterkeyhint");

// Enter on element; true when the page let it do what it does (send the form), false when the
// script stopped it.
function enter(element, init = {}) {
  element.focus();
  return element.dispatchEvent(
    new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true, ...init }),
  );
}

describe("Enter moves to the next field", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  // 22
  it("says 下一個 on every text field but the last", () => {
    page(REGISTER);
    for (const id of ["id_username", "id_email", "id_password1", "id_password2"]) {
      expect(hint(field(id)), id).toBe("next");
    }
    expect(hint(field("id_roc_birth_year"))).toBeNull();
    expect(document.querySelector('input[type="hidden"]').hasAttribute("enterkeyhint")).toBe(false);
    for (const button of document.querySelectorAll("button")) {
      expect(button.hasAttribute("enterkeyhint")).toBe(false);
    }
  });

  // 23
  it("moves to the next text field without sending the form", () => {
    page(REGISTER);
    expect(enter(field("id_username"))).toBe(false);
    expect(document.activeElement).toBe(field("id_email"));
    expect(enter(field("id_email"))).toBe(false);
    expect(document.activeElement).toBe(field("id_password1"));
  });

  // 24
  it("leaves Enter on the last field to send the form", () => {
    page(REGISTER);
    expect(enter(field("id_roc_birth_year"))).toBe(true);
    expect(document.activeElement).toBe(field("id_roc_birth_year"));
  });

  // 25
  it("leaves the Enter that picks a character alone", () => {
    page(REGISTER);
    expect(enter(field("id_username"), { isComposing: true })).toBe(true);
    expect(document.activeElement).toBe(field("id_username"));
    // Safari's Enter that ends the choosing comes after it, marked with keyCode 229.
    expect(enter(field("id_username"), { keyCode: 229 })).toBe(true);
    expect(document.activeElement).toBe(field("id_username"));
  });

  // 26
  it("goes from 密碼 to 密碼確認, past the 顯示 button", () => {
    page(REGISTER);
    enter(field("id_password1"));
    expect(document.activeElement).toBe(field("id_password2"));
    enter(field("id_password2"));
    expect(document.activeElement).toBe(field("id_roc_birth_year"));
  });

  it("still moves on once 顯示 has shown the password as text", () => {
    page(REGISTER);
    field("id_password1").type = "text";
    enter(field("id_password1"));
    expect(document.activeElement).toBe(field("id_password2"));
  });

  it("leaves other keys alone", () => {
    page(REGISTER);
    expect(enter(field("id_username"), { key: "a" })).toBe(true);
    expect(document.activeElement).toBe(field("id_username"));
  });

  // 27
  it("leaves a form with one text field as it was", () => {
    page(`
      <form method="post">
        <input type="hidden" name="csrfmiddlewaretoken" value="x">
        <input type="email" name="email" id="id_email">
        <button type="submit">寄重設信</button>
      </form>`);
    expect(field("id_email").hasAttribute("enterkeyhint")).toBe(false);
    expect(enter(field("id_email"))).toBe(true);
  });

  // 29: radios, ticks, lists and date pickers are not text fields.
  it("leaves radios, ticks, lists and date pickers alone and steps over them", () => {
    page(`
      <form method="post">
        <input type="text" id="first">
        <input type="radio" name="side" id="radio">
        <input type="checkbox" id="tick">
        <select id="list"><option>一</option></select>
        <input type="date" id="date">
        <input type="number" id="last">
      </form>`);
    for (const id of ["radio", "tick", "list", "date", "last"]) {
      expect(field(id).hasAttribute("enterkeyhint"), id).toBe(false);
    }
    for (const id of ["radio", "tick", "list", "date"]) {
      expect(enter(field(id)), id).toBe(true);
    }
    enter(field("first"));
    expect(document.activeElement).toBe(field("last"));
  });

  it("keeps each form's fields to itself", () => {
    page(`
      <form><input type="text" id="a1"><input type="text" id="a2"></form>
      <form><input type="text" id="b1"></form>`);
    enter(field("a1"));
    expect(document.activeElement).toBe(field("a2"));
    expect(hint(field("a2"))).toBeNull();
    expect(hint(field("b1"))).toBeNull();
  });

  // 30: only the script says 下一個; the page as sent does not.
  it("sets nothing before the script runs", () => {
    document.body.innerHTML = REGISTER;
    expect(document.querySelector("[enterkeyhint]")).toBeNull();
  });
});
