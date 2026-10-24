import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GIVE_BACK_AFTER, SHOW_AFTER, setUpPageLoading } from "./page-loading.js";

// A3 and C1, chosen by the site owner on the loading comparison page: a bar along the top with
// 載入中… when the next page takes a while, and 送出中… with a spinner on the pressed button.
// Each test gets its own document, so listeners from earlier tests never answer.
let doc;
let win;

function page(main) {
  doc = document.implementation.createHTMLDocument("");
  doc.body.innerHTML = `
    <div class="page-loading-bar" aria-hidden="true"></div>
    <p id="page-loading-status" class="page-loading-note" role="status"></p>
    <header><form id="logout-form" method="post"><button type="submit">登出</button></form></header>
    <main>${main}</main>`;
  win = Object.assign(new EventTarget(), {
    document: doc,
    location: { href: "https://hearwell.test/learn", origin: "https://hearwell.test" },
    setTimeout: (...args) => setTimeout(...args),
    clearTimeout: (id) => clearTimeout(id),
  });
  setUpPageLoading(win);
}

const loading = () => doc.documentElement.classList.contains("page-loading");
const status = () => doc.getElementById("page-loading-status").textContent;

function click(selector, options = {}) {
  const event = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0, ...options });
  doc.querySelector(selector).dispatchEvent(event);
  return event;
}

function submit(selector) {
  const button = doc.querySelector(selector);
  const event = new SubmitEvent("submit", { bubbles: true, cancelable: true, submitter: button });
  button.form.dispatchEvent(event);
  return event;
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("going to another page", () => {
  it("shows the bar and 載入中… only after a short wait", () => {
    page('<a href="/guide">選配指引</a>');
    click("a");
    vi.advanceTimersByTime(SHOW_AFTER - 1);
    expect(loading()).toBe(false);
    expect(status()).toBe("");
    vi.advanceTimersByTime(1);
    expect(loading()).toBe(true);
    expect(status()).toBe("載入中…");
  });

  it("clears when the page comes back from the back button", () => {
    page('<a href="/guide">選配指引</a>');
    click("a");
    vi.advanceTimersByTime(SHOW_AFTER);
    win.dispatchEvent(new Event("pageshow"));
    expect(loading()).toBe(false);
    expect(status()).toBe("");
  });

  it("gives up after 10 seconds without a new page", () => {
    page('<a href="/guide">選配指引</a>');
    click("a");
    vi.advanceTimersByTime(GIVE_BACK_AFTER);
    expect(loading()).toBe(false);
    expect(status()).toBe("");
  });

  it.each([
    ["a download", '<a href="/my_data/download" download>下載</a>', {}],
    ["another site", '<a href="https://www.mohw.gov.tw/">衛福部</a>', {}],
    ["a new tab", '<a href="/guide" target="_blank">選配指引</a>', {}],
    ["a section of this page", '<a href="#steps">步驟</a>', {}],
    ["a section of this page by its full path", '<a href="/learn#steps">步驟</a>', {}],
    ["a phone number", '<a href="tel:0800000000">撥打</a>', {}],
    ["a click with ctrl held", '<a href="/guide">選配指引</a>', { ctrlKey: true }],
    ["a middle click", '<a href="/guide">選配指引</a>', { button: 1 }],
  ])("stays off for %s", (_, link, options) => {
    page(link);
    click("a", options);
    vi.advanceTimersByTime(SHOW_AFTER);
    expect(loading()).toBe(false);
  });

  it("stays off when the page handles the click itself", () => {
    page('<a href="/guide">選配指引</a>');
    doc.querySelector("a").addEventListener("click", (event) => event.preventDefault());
    click("a");
    vi.advanceTimersByTime(SHOW_AFTER);
    expect(loading()).toBe(false);
  });

  it("shows for a link to another page with a section", () => {
    page('<a href="/guide#steps">選配步驟</a>');
    click("a");
    vi.advanceTimersByTime(SHOW_AFTER);
    expect(loading()).toBe(true);
  });

  it("shows for a search form, without touching its button", () => {
    page('<form method="get"><button type="submit">查詢</button></form>');
    submit("main button");
    expect(doc.querySelector("main button").textContent).toBe("查詢");
    vi.advanceTimersByTime(SHOW_AFTER);
    expect(loading()).toBe(true);
    expect(status()).toBe("載入中…");
  });
});

describe("sending a form", () => {
  const FORM = '<form method="post"><button type="submit" name="agree">我同意，開始篩檢</button></form>';
  const button = () => doc.querySelector("main button");

  it("says 送出中… with a spinner on the pressed button", () => {
    page(FORM);
    submit("main button");
    expect(button().textContent).toBe("送出中…");
    expect(button().querySelector(".spinner").getAttribute("aria-hidden")).toBe("true");
    expect(status()).toBe("送出中…");
    vi.advanceTimersByTime(SHOW_AFTER);
    expect(loading()).toBe(true);
    expect(status()).toBe("送出中…");
  });

  // The browser reads the pressed button's name and value right after the submit event and
  // skips disabled buttons, so disabling it at once would drop agree from the form.
  it("disables the button only after the browser has read it", () => {
    page(FORM);
    submit("main button");
    expect(button().disabled).toBe(false);
    vi.advanceTimersByTime(0);
    expect(button().disabled).toBe(true);
  });

  it("does not send twice", () => {
    page(FORM);
    expect(submit("main button").defaultPrevented).toBe(false);
    expect(submit("main button").defaultPrevented).toBe(true);
  });

  it("gives the button back after 10 seconds without an answer", () => {
    page(FORM);
    submit("main button");
    vi.advanceTimersByTime(GIVE_BACK_AFTER - 1);
    expect(button().disabled).toBe(true);
    vi.advanceTimersByTime(1);
    expect(button().disabled).toBe(false);
    expect(button().textContent).toBe("我同意，開始篩檢");
    expect(status()).toBe("");
    expect(submit("main button").defaultPrevented).toBe(false);
  });

  it("is a normal button again when the page comes back from the back button", () => {
    page(FORM);
    submit("main button");
    vi.advanceTimersByTime(SHOW_AFTER);
    win.dispatchEvent(new Event("pageshow"));
    expect(button().disabled).toBe(false);
    expect(button().textContent).toBe("我同意，開始篩檢");
    expect(loading()).toBe(false);
    // The earlier 10-second timer must not fire into a later submit.
    submit("main button");
    vi.advanceTimersByTime(GIVE_BACK_AFTER - 1);
    expect(button().disabled).toBe(true);
  });

  it("leaves forms that handle sending themselves alone", () => {
    page(FORM);
    button().form.addEventListener("submit", (event) => event.preventDefault());
    submit("main button");
    vi.advanceTimersByTime(SHOW_AFTER);
    expect(button().textContent).toBe("我同意，開始篩檢");
    expect(loading()).toBe(false);
  });

  it("keeps the header's 登出 button as it is", () => {
    page(FORM);
    submit("header button");
    expect(doc.querySelector("header button").textContent).toBe("登出");
    vi.advanceTimersByTime(SHOW_AFTER);
    expect(loading()).toBe(true);
    expect(status()).toBe("載入中…");
  });
});
