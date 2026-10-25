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
