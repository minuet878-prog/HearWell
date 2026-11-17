import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Spec #326 acceptance 8 (B3), ticket #332: the share page's copy button. A plain static file
// (not a Vite entry), so the test runs it as the page does.
const SCRIPT = resolve(process.cwd(), "../screening/static/screening/copy-link.js");

const button = () => document.getElementById("copy-link");
const status = () => document.getElementById("copy-status");

function page() {
  document.body.innerHTML = `
    <button id="copy-link" type="button" class="btn btn-outline-primary btn-lg" data-url="https://example.com/shared/abc" hidden>複製連結</button>
    <p id="copy-status" aria-live="polite"></p>
    <p id="share-url">可以複製這個網址傳給家人</p>`;
  new Function(readFileSync(SCRIPT, "utf-8"))();
}

// The clipboard answers in a later microtask; let it settle.
const copy = async () => {
  button().click();
  await vi.advanceTimersByTimeAsync(0);
};

describe("copy link button", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("isSecureContext", true);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn(() => Promise.resolve()) },
    });
    page();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    delete navigator.clipboard;
    document.body.innerHTML = "";
  });

  it("copies the link and the button itself says ✓ 已複製", async () => {
    await copy();
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("https://example.com/shared/abc");
    expect(button().textContent).toBe("已複製");
    // The ✓ is drawn, not read out: the button's name stays the words.
    const tick = button().querySelector("svg");
    expect(tick.getAttribute("aria-hidden")).toBe("true");
  });

  it("goes back to 複製連結 after 2 seconds", async () => {
    await copy();
    await vi.advanceTimersByTimeAsync(1999);
    expect(button().textContent).toBe("已複製");
    await vi.advanceTimersByTimeAsync(1);
    expect(button().textContent).toBe("複製連結");
    expect(button().querySelector("svg")).toBeNull();
  });

  it("says 已複製 again in the status area on every press", async () => {
    await copy();
    await vi.advanceTimersByTimeAsync(100);
    expect(status().textContent).toBe("已複製");
    // A second press while the first is still showing: the words are written anew, so a screen
    // reader reads them again.
    await copy();
    expect(status().textContent).toBe("");
    await vi.advanceTimersByTimeAsync(100);
    expect(status().textContent).toBe("已複製");
  });

  it("a second press keeps ✓ 已複製 for 2 seconds from that press", async () => {
    await copy();
    await vi.advanceTimersByTimeAsync(1500);
    await copy();
    await vi.advanceTimersByTimeAsync(1500);
    expect(button().textContent).toBe("已複製");
    await vi.advanceTimersByTimeAsync(500);
    expect(button().textContent).toBe("複製連結");
  });

  // #366 (spec #354): without the phone's share sheet, copying is the way to send, so the
  // button is the solid main one; beside 再傳一次給家人 it stays the outline second.
  it("is the solid main button without a share sheet", () => {
    expect(navigator.share).toBeUndefined();
    expect(button().className).toBe("btn btn-primary btn-lg");
  });

  it("stays the outline button beside a share sheet", () => {
    vi.stubGlobal("navigator", Object.assign(Object.create(navigator), { share: vi.fn() }));
    page();
    expect(button().className).toBe("btn btn-outline-primary btn-lg");
  });

  it("shows the address instead when the browser refuses to copy", async () => {
    navigator.clipboard.writeText.mockImplementation(() => Promise.reject(new Error("denied")));
    await copy();
    expect(document.getElementById("share-url").hidden).toBe(false);
    expect(button().textContent).toBe("複製連結");
    expect(status().textContent).toBe("");
  });
});

// #361 (spec #354): the family page's 複製網址, for browsers with no share sheet. The address
// stays on the page above it, and on a phone with a share sheet 傳給家人 is the only button.
describe("family page copy button", () => {
  function familyPage() {
    document.body.innerHTML = `
      <p>可以複製這個網址傳給家人：<span>https://example.com/family</span></p>
      <button id="copy-link" type="button" data-url="https://example.com/family" data-without-share-sheet hidden>複製網址</button>
      <p id="copy-status" aria-live="polite"></p>`;
    new Function(readFileSync(SCRIPT, "utf-8"))();
  }

  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("isSecureContext", true);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn(() => Promise.resolve()) },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    delete navigator.clipboard;
    delete navigator.share;
    document.body.innerHTML = "";
  });

  it("shows under the address, which stays, and copies it with ✓ 已複製", async () => {
    familyPage();
    expect(button().hidden).toBe(false);
    expect(document.body.textContent).toContain("https://example.com/family");
    await copy();
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("https://example.com/family");
    expect(button().textContent).toBe("已複製");
    await vi.advanceTimersByTimeAsync(100);
    expect(status().textContent).toBe("已複製");
    await vi.advanceTimersByTimeAsync(1900);
    expect(button().textContent).toBe("複製網址");
  });

  it("stays hidden where the phone's share sheet is", () => {
    Object.defineProperty(navigator, "share", { configurable: true, value: vi.fn() });
    familyPage();
    expect(button().hidden).toBe(true);
  });
});

// Spec #655 (#674) acceptance 19: 傳給他's 複製訊息 copies the whole message and address the
// page shows (data-text), only where the phone's share sheet is not, and keeps its own style.
describe("send-to-him copy button", () => {
  const TEXT = "分享你一個聽力自我篩檢。\nhttps://example.com/questionnaire_list?via=send";

  function sendPage(style) {
    document.body.innerHTML = `
      <div><p>分享你一個聽力自我篩檢。<br>https://example.com/questionnaire_list?via=send</p></div>
      <button id="copy-link" type="button" class="btn ${style} btn-lg" data-text="${TEXT}" data-without-share-sheet hidden>複製訊息</button>
      <p id="copy-status" aria-live="polite"></p>`;
    new Function(readFileSync(SCRIPT, "utf-8"))();
  }

  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("isSecureContext", true);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn(() => Promise.resolve()) },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    delete navigator.clipboard;
    delete navigator.share;
    document.body.innerHTML = "";
  });

  it("copies the message and the address as one text and says ✓ 已複製", async () => {
    sendPage("btn-primary");
    expect(button().hidden).toBe(false);
    await copy();
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(TEXT);
    expect(button().textContent).toBe("已複製");
    await vi.advanceTimersByTimeAsync(2000);
    expect(button().textContent).toBe("複製訊息");
  });

  it("keeps the outline style the page gave it", () => {
    sendPage("btn-outline-primary");
    expect(button().classList.contains("btn-outline-primary")).toBe(true);
    expect(button().classList.contains("btn-primary")).toBe(false);
  });

  it("stays hidden where the phone's share sheet is", () => {
    Object.defineProperty(navigator, "share", { configurable: true, value: vi.fn() });
    sendPage("btn-primary");
    expect(button().hidden).toBe(true);
  });
});

// #580 (spec #576 acceptance 21 to 24): 複製信箱 beside the contact address, in the footer of
// every page and beside the account page's sentence; several on one page, each its own.
describe("contact address copy buttons", () => {
  const ADDRESS = "hearwellweb@gmail.com";
  const buttons = () => [...document.querySelectorAll("[data-copy]")];
  const said = () => document.querySelector("[data-copy-status]");

  function pageWithTwo() {
    document.body.innerHTML = `
      <p>要修改請寫信到 <a href="mailto:${ADDRESS}">${ADDRESS}</a></p>
      <button type="button" class="btn btn-outline-primary" data-copy="${ADDRESS}" hidden><svg aria-hidden="true"></svg>複製信箱</button>
      <footer>
        <a href="mailto:${ADDRESS}">${ADDRESS}</a>
        <button type="button" class="btn btn-outline-primary" data-copy="${ADDRESS}" hidden><svg aria-hidden="true"></svg>複製信箱</button>
        <p aria-live="polite" data-copy-status></p>
      </footer>`;
    new Function(readFileSync(SCRIPT, "utf-8"))();
  }

  const press = async (button) => {
    button.click();
    await vi.advanceTimersByTimeAsync(0);
  };

  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("isSecureContext", true);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn(() => Promise.resolve()) },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    delete navigator.clipboard;
    delete navigator.share;
    document.body.innerHTML = "";
  });

  it("copies the address and only the pressed button says ✓ 已複製", async () => {
    pageWithTwo();
    const [inPage, inFooter] = buttons();
    expect(inPage.hidden).toBe(false);
    expect(inFooter.hidden).toBe(false);
    await press(inFooter);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(ADDRESS);
    expect(inFooter.textContent).toBe("已複製");
    expect(inFooter.classList.contains("is-copied")).toBe(true);
    expect(inPage.textContent).toBe("複製信箱");
    expect(inPage.classList.contains("is-copied")).toBe(false);
  });

  it("goes back to 複製信箱 with its icon after 2 seconds", async () => {
    pageWithTwo();
    const [inPage] = buttons();
    const before = inPage.innerHTML;
    await press(inPage);
    await vi.advanceTimersByTimeAsync(1999);
    expect(inPage.textContent).toBe("已複製");
    await vi.advanceTimersByTimeAsync(1);
    expect(inPage.innerHTML).toBe(before);
    expect(inPage.classList.contains("is-copied")).toBe(false);
  });

  it("says 已複製 again on every press, the same button or the other", async () => {
    pageWithTwo();
    const [inPage, inFooter] = buttons();
    await press(inPage);
    await vi.advanceTimersByTimeAsync(100);
    expect(said().textContent).toBe("已複製");
    await press(inPage);
    expect(said().textContent).toBe("");
    await vi.advanceTimersByTimeAsync(100);
    expect(said().textContent).toBe("已複製");
    await press(inFooter);
    expect(said().textContent).toBe("");
    await vi.advanceTimersByTimeAsync(100);
    expect(said().textContent).toBe("已複製");
  });

  it("the mail link stays as it was", async () => {
    pageWithTwo();
    await press(buttons()[0]);
    expect(document.querySelector("footer a").getAttribute("href")).toBe(`mailto:${ADDRESS}`);
  });

  // Spec #576 user story 28: no button that does nothing. The address is still beside it.
  it("goes away when the browser refuses to copy, the other one staying", async () => {
    navigator.clipboard.writeText.mockImplementation(() => Promise.reject(new Error("denied")));
    pageWithTwo();
    const [inPage, inFooter] = buttons();
    await press(inPage);
    expect(inPage.hidden).toBe(true);
    expect(inFooter.hidden).toBe(false);
    expect(said().textContent).toBe("");
    expect(document.body.textContent).toContain(ADDRESS);
  });

  it("stay hidden where the browser cannot copy", () => {
    delete navigator.clipboard;
    pageWithTwo();
    expect(buttons().map((b) => b.hidden)).toEqual([true, true]);
  });

  it("stay hidden on a page that is not secure", () => {
    vi.stubGlobal("isSecureContext", false);
    pageWithTwo();
    expect(buttons().map((b) => b.hidden)).toEqual([true, true]);
  });

  it("work beside the family page's button that a share sheet keeps hidden", async () => {
    Object.defineProperty(navigator, "share", { configurable: true, value: vi.fn() });
    document.body.innerHTML = `
      <button id="copy-link" type="button" data-url="https://example.com/family" data-without-share-sheet hidden>複製網址</button>
      <p id="copy-status" aria-live="polite"></p>
      <button type="button" data-copy="${ADDRESS}" hidden>複製信箱</button>
      <p aria-live="polite" data-copy-status></p>`;
    new Function(readFileSync(SCRIPT, "utf-8"))();
    expect(document.getElementById("copy-link").hidden).toBe(true);
    await press(buttons()[0]);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(ADDRESS);
    expect(buttons()[0].textContent).toBe("已複製");
  });
});
