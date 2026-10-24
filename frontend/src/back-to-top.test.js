import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// #335 (spec #326 E1, acceptance 20 and 23): the long pages' 回到頂端 button. A plain static file
// (not a Vite entry), so the test runs it as the page does.
const SCRIPT = resolve(process.cwd(), "../screening/static/screening/back-to-top.js");

const button = () => document.querySelector("main button");
const heading = () => document.querySelector("main h1");

function scrollTo(y) {
  window.scrollY = y;
  window.dispatchEvent(new Event("scroll"));
}

function page({ reducedMotion = false } = {}) {
  document.body.innerHTML = `
    <header><p>HearWell</p></header>
    <nav class="site-nav" aria-label="主要導覽"></nav>
    <main>
      <h1>我的選配指引</h1>
      <p>很長的內容</p>
      <button id="back-to-top" type="button" hidden>回到頂端</button>
    </main>`;
  window.matchMedia = vi.fn((query) => ({
    matches: reducedMotion && query === "(prefers-reduced-motion: reduce)",
  }));
  window.scrollTo = vi.fn();
  new Function(readFileSync(SCRIPT, "utf-8"))();
}

describe("back to top", () => {
  beforeEach(() => {
    window.innerHeight = 800;
    window.scrollY = 0;
  });

  afterEach(() => {
    document.body.innerHTML = "";
    delete window.matchMedia;
  });

  it("stays hidden within the first screen", () => {
    page();
    scrollTo(800);
    expect(button().hidden).toBe(true);
  });

  it("shows once the page has scrolled past one screen, and hides again above it", () => {
    page();
    scrollTo(801);
    expect(button().hidden).toBe(false);
    scrollTo(300);
    expect(button().hidden).toBe(true);
  });

  it("shows straight away on a page that opens already scrolled down", () => {
    window.scrollY = 2000;
    page();
    expect(button().hidden).toBe(false);
  });

  it("scrolls smoothly to the top and puts focus on the page title", () => {
    page();
    scrollTo(2000);
    button().click();
    expect(window.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" });
    expect(document.activeElement).toBe(heading());
  });

  it("jumps without scrolling motion when reduced motion is on", () => {
    page({ reducedMotion: true });
    scrollTo(2000);
    button().click();
    // "auto" follows the CSS, which only scrolls smoothly without reduced motion (site.css).
    expect(window.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "auto" });
    expect(document.activeElement).toBe(heading());
  });
});
