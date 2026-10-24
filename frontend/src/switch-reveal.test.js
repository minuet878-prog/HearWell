import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

// Spec #326 D3 (#334): a page that paints before its switch is parsed would fade the old pill
// out instead of sliding it, so it changes page without the transition. A plain static file
// (not a Vite entry), so the test runs it as the page does.
const SCRIPT = resolve(process.cwd(), "../screening/static/screening/switch-reveal.js");

const run = () => new Function(readFileSync(SCRIPT, "utf-8"))();

function reveal(viewTransition) {
  const event = new Event("pagereveal");
  event.viewTransition = viewTransition;
  window.dispatchEvent(event);
}

describe("switch reveal", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("skips the transition when the page paints before its switch is parsed", () => {
    run();
    const transition = { skipTransition: vi.fn() };
    reveal(transition);
    expect(transition.skipTransition).toHaveBeenCalled();
  });

  it.each([
    ['<nav class="records-switch"><a href="/a" aria-current="page">問卷</a></nav>'],
    ['<nav class="ear-switch"><a href="/b" aria-current="true">右耳</a></nav>'],
  ])("lets the pill slide once the switch is there: %s", (switchHtml) => {
    document.body.innerHTML = switchHtml;
    run();
    const transition = { skipTransition: vi.fn() };
    reveal(transition);
    expect(transition.skipTransition).not.toHaveBeenCalled();
  });

  it("does nothing on a change of page without a transition", () => {
    run();
    expect(() => reveal(null)).not.toThrow();
  });
});
