import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AudiogramDemo from "./AudiogramDemo.jsx";

// #618 (spec #611 K2, the #613 mockup's part five): 看示範 plays a finger tapping 1000 Hz 45 dB on
// a small chart of its own, once, in about 2 seconds, as the mockup's table of moves times it.
let reduce;
beforeEach(() => {
  reduce = false;
  window.matchMedia = (query) => ({ matches: query === "(prefers-reduced-motion: reduce)" && reduce });
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  cleanup();
});

const demo = () => document.querySelector(".audiogram-demo");
const shown = () => [...demo().querySelector(".audiogram-reading").children].map((row) => row.textContent);
const finger = () => demo().querySelector(".audiogram-demo-finger").getAttribute("transform");
const mark = () => demo().querySelector(".audiogram-demo-mark");
const ring = () => demo().querySelector(".audiogram-demo-ring");
const button = () => screen.getByRole("button");
const wait = (ms) => act(() => vi.advanceTimersByTime(ms));
const HINT = ["點一下圖來標記"];
// The mockup's frames 1 and 4: the finger in the bottom right corner, before and after.
const START = "translate(273 218) rotate(30) scale(1.05)";
const END = "translate(261 212) rotate(30) scale(1.05)";
const ON_THE_POINT = "translate(151.2 169) rotate(38) scale(1.05)";

describe("AudiogramDemo", () => {
  it("waits on the first frame with 看示範, and never plays by itself (acceptance 42, 45)", () => {
    render(<AudiogramDemo ear="right" />);
    expect(screen.getByRole("button", { name: "看示範" }).textContent).toBe("▶ 看示範");
    expect(button().type).toBe("button");
    // The mockup: an outline button, the page has a solid 下一步 already.
    expect(button().classList.contains("btn-outline-primary")).toBe(true);
    wait(5000);
    expect(finger()).toBe(START);
    expect(mark()).toBeNull();
    expect(shown()).toEqual(HINT);
  });

  // Acceptance 48: the three steps in words say it all; the demo is only another way to see it.
  it("keeps the demo itself from screen readers, the button only is heard", () => {
    render(<AudiogramDemo ear="right" />);
    expect(demo().getAttribute("aria-hidden")).toBe("true");
    expect(demo().contains(button())).toBe(false);
    expect(demo().querySelector("[role=status]")).toBeNull();
  });

  it("moves the finger to 1000 Hz 45 dB, taps, and the mark and its reading come up (acceptance 43)", () => {
    render(<AudiogramDemo ear="right" />);
    fireEvent.click(button());
    expect(finger()).toBe(START);
    wait(300);
    expect(finger()).toBe(START);
    // Half way through 0.3-1.1 s it is half way along the straight line (eased in and out).
    wait(400);
    const [px, py] = finger().match(/-?[\d.]+/g).map(Number);
    expect((273 - px) / (273 - 151.2)).toBeCloseTo(0.5, 1);
    expect((218 - py) / (218 - 169)).toBeCloseTo((273 - px) / (273 - 151.2), 1);
    expect(mark()).toBeNull();
    expect(shown()).toEqual(HINT);
    wait(420);
    expect(finger()).toBe(ON_THE_POINT);
    expect(mark().getAttribute("class")).toContain("ear-right");
    expect(shown()).toEqual(["右耳氣導", "1000 Hz　45 dB"]);
    // The dashed ring shows at the tap and fades by 1.4 s.
    expect(Number(ring().getAttribute("opacity"))).toBeGreaterThan(0.8);
    wait(150);
    expect(Number(ring().getAttribute("opacity"))).toBeLessThan(0.6);
    wait(200);
    expect(ring()).toBeNull();
  });

  it("stops on the last frame after 2 seconds, and offers 再看一次 (acceptance 43, 44)", () => {
    render(<AudiogramDemo ear="right" />);
    fireEvent.click(button());
    wait(1900);
    expect(screen.getByRole("button", { name: "看示範" })).toBeDefined();
    wait(120);
    expect(finger()).toBe(END);
    expect(mark()).not.toBeNull();
    expect(shown()).toEqual(["右耳氣導", "1000 Hz　45 dB"]);
    expect(screen.getByRole("button", { name: "再看一次" }).textContent).toBe("↺ 再看一次");
    // No loop: it stays as it stopped.
    wait(5000);
    expect(finger()).toBe(END);
    expect(mark()).not.toBeNull();
  });

  it("plays again from the start on 再看一次 (acceptance 44)", () => {
    render(<AudiogramDemo ear="right" />);
    fireEvent.click(button());
    wait(2100);
    fireEvent.click(screen.getByRole("button", { name: "再看一次" }));
    expect(finger()).toBe(START);
    expect(mark()).toBeNull();
    expect(shown()).toEqual(HINT);
    wait(2100);
    expect(finger()).toBe(END);
    expect(shown()).toEqual(["右耳氣導", "1000 Hz　45 dB"]);
  });

  // The owner's pick (the mockup's A): the symbol of the step's ear.
  it("shows the left ear's ✕ on the left ear's step", () => {
    render(<AudiogramDemo ear="left" />);
    fireEvent.click(button());
    wait(2100);
    expect(mark().getAttribute("class")).toContain("ear-left");
    expect(mark().tagName).toBe("path");
    expect(shown()).toEqual(["左耳氣導", "1000 Hz　45 dB"]);
  });

  // Acceptance 47.
  it("is not there with reduced motion", () => {
    reduce = true;
    render(<AudiogramDemo ear="right" />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(demo()).toBeNull();
  });
});
