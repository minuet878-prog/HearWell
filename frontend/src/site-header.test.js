import { beforeEach, describe, expect, it, vi } from "vitest";

import { setUpAccountMenu, setUpSiteHeader } from "./site-header.js";

// #748 (spec #741 acceptance 38, 39, story 51; ADR 0079). jsdom neither scrolls nor leaves the
// page, so a stand-in window holds where the page is, its history and where it came from.
function fakeWindow({ canGoBack, historyLength = 1, referrer = "" } = {}) {
  const win = new EventTarget();
  Object.assign(win, {
    document,
    scrollY: 0,
    history: { length: historyLength, back: vi.fn() },
    // undefined: a browser without the Navigation API.
    navigation: canGoBack === undefined ? undefined : { canGoBack },
    location: { origin: "https://tingpal.tw" },
    scrollTo(y) {
      win.scrollY = y;
      win.dispatchEvent(new Event("scroll"));
    },
  });
  Object.defineProperty(document, "referrer", { value: referrer, configurable: true });
  return win;
}

const header = () => document.querySelector(".site-header");
const back = () => document.querySelector("[data-site-back]");
const isScrolled = () => header().hasAttribute("data-scrolled");

// A click the way the browser sends it, so a test can see whether the link was followed.
function press() {
  const event = new MouseEvent("click", { bubbles: true, cancelable: true });
  back().dispatchEvent(event);
  return event;
}

beforeEach(() => {
  document.body.innerHTML = `
    <header class="site-header">
      <p class="site-brand"><a href="/">聽伴</a></p>
      <a class="site-back" href="/" aria-label="回首頁" data-site-back></a>
    </header>
    <main></main>`;
  Object.defineProperty(header(), "offsetHeight", { value: 72, configurable: true });
});

describe("scrolling past the header", () => {
  it("swaps the name for the back button, and back at the top swaps them again", () => {
    const win = fakeWindow();
    setUpSiteHeader(win);
    expect(isScrolled()).toBe(false);
    win.scrollTo(40);
    expect(isScrolled()).toBe(false);
    win.scrollTo(200);
    expect(isScrolled()).toBe(true);
    win.scrollTo(0);
    expect(isScrolled()).toBe(false);
  });

  it("starts swapped on a page opened partway down (back from the next page)", () => {
    const win = fakeWindow();
    win.scrollY = 500;
    setUpSiteHeader(win);
    expect(isScrolled()).toBe(true);
  });
});

describe("the back button", () => {
  it.each([
    ["the Navigation API", { canGoBack: true, historyLength: 1 }],
    [
      "history and a page of this site before it",
      { historyLength: 2, referrer: "https://tingpal.tw/learn" },
    ],
  ])("goes to the previous page of this site, judged by %s", (_, options) => {
    const win = fakeWindow(options);
    setUpSiteHeader(win);
    expect(back().getAttribute("aria-label")).toBe("回上一頁");
    const event = press();
    expect(win.history.back).toHaveBeenCalledOnce();
    expect(event.defaultPrevented).toBe(true);
  });

  // Opened from LINE or typed in: the link's own way home is followed.
  it.each([
    ["the Navigation API", { canGoBack: false, historyLength: 3 }],
    ["history alone", { historyLength: 1 }],
    ["a page of another site before it", { historyLength: 2, referrer: "https://line.me/" }],
    ["no page named before it", { historyLength: 2 }],
  ])("goes home when nothing of this site is before it, judged by %s", (_, options) => {
    const win = fakeWindow(options);
    setUpSiteHeader(win);
    expect(back().getAttribute("aria-label")).toBe("回首頁");
    const event = press();
    expect(win.history.back).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });
});

// #755 (spec #741 P21): the answer page has 離開 in its place, a plain link out to the
// questionnaires; the back button there would go back a question.
describe("a page without the back button", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <header class="site-header">
        <a class="site-leave" href="/questionnaire_list">離開</a>
      </header>
      <main></main>`;
    Object.defineProperty(header(), "offsetHeight", { value: 72, configurable: true });
  });

  it("still marks the header scrolled, and leaves 離開 a plain link", () => {
    const win = fakeWindow({ canGoBack: true });
    setUpSiteHeader(win);
    win.scrollTo(200);
    expect(isScrolled()).toBe(true);
    const event = new MouseEvent("click", { bubbles: true, cancelable: true });
    document.querySelector(".site-leave").dispatchEvent(event);
    expect(win.history.back).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });
});

// Spec #741 at acceptance (2026-11-21, compare-avatar-menu.html A): signed in, tapping the
// avatar opens a small menu of 帳號設定 and 登出. The page has both the link (no JavaScript) and
// the menu button, hidden; this swaps them.
describe("the avatar menu", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <header class="site-header">
        <div class="site-account" data-site-account>
          <a class="site-avatar" href="/account" aria-label="帳號設定：jason">J</a>
          <button class="site-avatar" type="button" aria-label="帳號選單：jason"
            aria-expanded="false" aria-controls="site-account-menu" hidden
            data-site-account-toggle>J</button>
          <div class="site-account-menu" id="site-account-menu" hidden>
            <p class="site-account-name">jason</p>
            <a class="site-account-item" href="/account">帳號設定</a>
            <form id="header-logout-form" action="/logout" method="post">
              <button class="site-account-item site-account-logout" type="submit">登出</button>
            </form>
          </div>
        </div>
      </header>
      <main><p>內容</p><a href="/learn">了解</a></main>`;
    setUpAccountMenu();
  });

  const link = () => document.querySelector("a.site-avatar");
  const avatar = () => document.querySelector("[data-site-account-toggle]");
  const menu = () => document.getElementById("site-account-menu");
  const isOpen = () => !menu().hidden && avatar().getAttribute("aria-expanded") === "true";
  const isClosed = () => menu().hidden && avatar().getAttribute("aria-expanded") === "false";
  const click = (element) => element.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  const pressKey = (key) =>
    document.activeElement.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));

  it("puts the menu button in place of the link to account settings", () => {
    expect(link().hidden).toBe(true);
    expect(avatar().hidden).toBe(false);
    expect(isClosed()).toBe(true);
  });

  it("opens on tapping the avatar, with the focus on 帳號設定", () => {
    click(avatar());
    expect(isOpen()).toBe(true);
    expect(document.activeElement.textContent).toBe("帳號設定");
  });

  it("closes on tapping the avatar again, with the focus back on it", () => {
    click(avatar());
    click(avatar());
    expect(isClosed()).toBe(true);
    expect(document.activeElement).toBe(avatar());
  });

  // A finger or mouse going down, which an iPhone sends for a tap on plain text too.
  const touch = (element) =>
    element.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true }));

  it("stays open on tapping inside it", () => {
    click(avatar());
    touch(document.querySelector(".site-account-name"));
    expect(isOpen()).toBe(true);
  });

  it("closes on tapping outside it, with the focus back on the avatar", () => {
    click(avatar());
    touch(document.querySelector("main p"));
    expect(isClosed()).toBe(true);
    expect(document.activeElement).toBe(avatar());
  });

  // Tabbed out of the menu, it closes on its own and leaves the focus where it landed.
  it("closes when focus leaves the menu without pulling focus back", () => {
    click(avatar());
    const learn = document.querySelector("main a");
    const firstItem = document.querySelector(".site-account-item");
    learn.focus();
    firstItem.dispatchEvent(new FocusEvent("focusout", { bubbles: true, relatedTarget: learn }));
    expect(isClosed()).toBe(true);
    expect(document.activeElement).toBe(learn);
  });

  // Moving focus between items inside the menu, or clicking non-focusable text in it, keeps it open.
  it("stays open when focus moves inside the menu or clears on inner text", () => {
    click(avatar());
    const [settings, logout] = document.querySelectorAll(".site-account-item");
    settings.dispatchEvent(new FocusEvent("focusout", { bubbles: true, relatedTarget: logout }));
    expect(isOpen()).toBe(true);
    logout.dispatchEvent(new FocusEvent("focusout", { bubbles: true, relatedTarget: null }));
    expect(isOpen()).toBe(true);
  });

  // Tabbed out of the menu, a tap outside leaves the focus where it was.
  it("leaves the focus alone once it has left the menu", () => {
    click(avatar());
    const learn = document.querySelector("main a");
    learn.focus();
    touch(learn);
    expect(isClosed()).toBe(true);
    expect(document.activeElement).toBe(learn);
  });

  it("closes on Escape, with the focus back on the avatar", () => {
    click(avatar());
    pressKey("Escape");
    expect(isClosed()).toBe(true);
    expect(document.activeElement).toBe(avatar());
  });

  it("leaves Escape alone while closed", () => {
    const learn = document.querySelector("main a");
    learn.focus();
    pressKey("Escape");
    expect(isClosed()).toBe(true);
    expect(document.activeElement).toBe(learn);
  });

  it("does nothing on a page signed out", () => {
    document.body.innerHTML = '<header class="site-header"><a href="/login">登入</a></header>';
    expect(() => setUpAccountMenu()).not.toThrow();
  });
});
