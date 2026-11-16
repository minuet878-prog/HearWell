import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The feedback batch (the owner's F4 B): 下載我的資料 says the download has started and where the
// file goes. A plain static file (not a Vite entry), so the test runs it as the page does.
const SCRIPT = resolve(process.cwd(), "../screening/static/screening/download-note.js");
const STARTED = "已開始下載，請到手機的「下載項目」找。";

const link = () => document.querySelector("[data-download-note]");
const words = () => document.querySelector("[data-download-words]");
const status = () => document.querySelector("[data-download-status]");

describe("download started note", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    document.body.innerHTML = `
      <ul><li>
        <a class="link-card action-card" href="/download" download data-download-note>
          <span class="action-card-icon" aria-hidden="true"><svg><path d="M12 3v12"/></svg></span>
          <span class="link-card-body">
            <span class="link-card-title">下載我的資料</span>
            <span data-download-words>把您在聽伴的所有資料下載成一個檔案保存。</span>
          </span>
        </a>
        <span class="visually-hidden" role="status" data-download-status></span>
      </li></ul>`;
    // The click would start a real download; the test only watches what the page says.
    link().addEventListener("click", (event) => event.preventDefault());
    new Function(readFileSync(SCRIPT, "utf-8"))();
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("says nothing new before a press", () => {
    expect(words().textContent).toBe("把您在聽伴的所有資料下載成一個檔案保存。");
    expect(link().classList.contains("is-download-started")).toBe(false);
  });

  it("a press says it has started and where to find the file, in green with a tick", () => {
    link().click();
    expect(words().textContent).toBe(`✓ ${STARTED}`);
    expect(link().classList.contains("is-download-started")).toBe(true);
    expect(link().querySelector(".action-card-icon path").getAttribute("d")).toBe(
      "M5 12.5l4.5 4.5L19 7.5",
    );
  });

  it("tells screen readers, without the tick, and again on a second press", () => {
    link().click();
    vi.advanceTimersByTime(100);
    expect(status().textContent).toBe(STARTED);
    link().click();
    expect(status().textContent).toBe("");
    vi.advanceTimersByTime(100);
    expect(status().textContent).toBe(STARTED);
  });

  it("stays until the page is left, as the site's other done notes do", () => {
    link().click();
    vi.advanceTimersByTime(60_000);
    expect(words().textContent).toBe(`✓ ${STARTED}`);
  });
});
