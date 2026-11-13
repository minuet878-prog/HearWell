import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { addMotionButtons } from "./wear-motion.js";

// Spec #519, tickets #521 and #522: 看動作 under the 怎麼戴上、拿下 drawings that carry a motion
// (wear-motion-review.md's table). The page is what the server sends: pick-explain.html's question
// with a shape's steps folded away, each step care_step.html's drawing and box.
const PICK_EXPLAIN = resolve(process.cwd(), "../screening/static/screening/pick-explain.js");

// A drawing as the care_drawings files draw it: an outer scale group whose children are the
// pieces the motion counts from 0.
const drawing = (motion, pieces) =>
  `<svg class="care-drawing" viewBox="0 0 240 160" aria-hidden="true" focusable="false"${
    motion ? ` data-motion='${JSON.stringify(motion)}'` : ""
  }><g transform="scale(0.2)">${pieces}</g></svg>`;

// Push in: piece 1 slides from (80, -55) to where it is drawn, between 15% and 75% of the play;
// piece 0 is a line whose second point follows it; piece 2 is the arrow.
const PUSH_IN = {
  parts: [{ pieces: [1], pivot: [0, 0], keys: [[15, 80, -55, 0], [75, 0, 0, 0]] }],
  lines: [{ pieces: [0], with: 0, points: [1] }],
  cues: [2],
};
const PUSH_IN_PIECES =
  '<path d="M100 100C120 100 140 120 160 140"/>' +
  '<g transform="translate(846 628)"><rect x="16" y="-15" width="70" height="30"/></g>' +
  '<path d="M1060 500C1010 512 960 546 932 582"/>';

const step = (title, svg) =>
  `<li>${svg}<label class="visit-check"><input type="checkbox" autocomplete="off"><span><strong class="block">${title}</strong>words</span></label></li>`;

const serverPage = () => {
  document.body.innerHTML = `
    <fieldset data-pick-explain>
      <legend>他的助聽器是哪一種？</legend>
      <label><input type="radio" name="hearing-aid-wear"><span>耳掛（耳塞和細線）</span></label>
      <label><input type="radio" name="hearing-aid-wear"><span>耳內</span></label>
      <ul data-pick-explanations>
        <li><strong>耳掛（耳塞和細線）</strong><ol>
          ${step("1. 分左右", drawing(null, "<path d='M0 0'/>"))}
          ${step("4. 推進耳塞", drawing(PUSH_IN, PUSH_IN_PIECES))}
        </ol></li>
        <li><strong>耳內</strong><ol>
          ${step("3. 對準耳道", drawing(null, "<path d='M0 0'/>"))}
        </ol></li>
      </ul>
      <div aria-live="polite" data-pick-live></div>
    </fieldset>`;
};

function fakeWindow({ reduce = false } = {}) {
  window.matchMedia = (query) => ({
    matches: query === "(prefers-reduced-motion: reduce)" && reduce,
  });
  return window;
}

const buttons = (root = document) => [...root.querySelectorAll("button")];

describe("addMotionButtons", () => {
  beforeEach(serverPage);

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("puts 看動作 under each drawing with a motion, and under no other", () => {
    addMotionButtons(fakeWindow());
    const [button, ...others] = buttons();
    expect(others).toEqual([]);
    expect(button.textContent).toContain("看動作");
    expect(button.previousElementSibling.dataset.motion).toBeDefined();
    expect(button.type).toBe("button");
  });

  // #519 acceptance 8: reduced motion keeps the reviewed drawing, with no button to press.
  it("adds no button with reduced motion", () => {
    addMotionButtons(fakeWindow({ reduce: true }));
    expect(buttons()).toEqual([]);
  });

  // Acceptance 11: a row of buttons each heard as which step's motion, not a row of 看動作.
  it("names each button after its step's title, without its number", () => {
    addMotionButtons(fakeWindow());
    expect(buttons()[0].getAttribute("aria-label")).toBe("看動作：推進耳塞");
    expect(buttons()[0].textContent).toBe("▶ 看動作");
  });
});

// The pieces of a drawing, counted as the motion counts them.
const pieces = (svg) => [...svg.firstElementChild.children];
const arrowsGone = (svg) => pieces(svg)[2].getAttribute("visibility") === "hidden";
const words = (button) => button.textContent.slice(2);

describe("playing a motion", () => {
  let svg;
  let button;

  beforeEach(() => {
    vi.useFakeTimers();
    serverPage();
    addMotionButtons(fakeWindow());
    [button] = buttons();
    svg = button.previousElementSibling;
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  // Acceptance 3: from outside the ear, arrows gone, the line's end with the dome.
  it("starts from where the motion starts, with the arrows gone", () => {
    button.click();
    expect(pieces(svg)[1].getAttribute("transform")).toBe(
      "translate(80 -55) rotate(0 0 0) translate(846 628)",
    );
    expect(pieces(svg)[0].getAttribute("d")).toBe("M100 100C200 45 140 120 160 140");
    expect(arrowsGone(svg)).toBe(true);
  });

  // Waits at the start until 15%, then eases: half way between 15% and 75% it is half way there.
  it("is still at the start at 15% and half way there at 45%", () => {
    button.click();
    vi.advanceTimersByTime(350);
    expect(pieces(svg)[1].getAttribute("transform")).toMatch(/^translate\(80 -55\)/);
    vi.advanceTimersByTime(1080 - 350);
    // Within a frame (16ms) of half way, on the straight line between.
    const [right, down] = pieces(svg)[1].getAttribute("transform").match(/-?[\d.]+/g).map(Number);
    expect(right / 80).toBeCloseTo(0.5, 1);
    expect(down / -55).toBeCloseTo(right / 80, 2);
    expect(words(button)).toBe("看動作");
  });

  // Acceptance 3: it stops on the reviewed drawing, arrows still gone, and offers to play again.
  it("stops on the reviewed drawing after 2.4 seconds and says 再看一次", () => {
    button.click();
    vi.advanceTimersByTime(2400);
    expect(pieces(svg)[1].getAttribute("transform")).toBe("translate(846 628)");
    expect(pieces(svg)[0].getAttribute("d")).toBe("M100 100C120 100 140 120 160 140");
    expect(arrowsGone(svg)).toBe(true);
    expect(words(button)).toBe("再看一次");
    expect(button.getAttribute("aria-label")).toBe("再看一次：推進耳塞");
    expect(button.textContent).toBe("↺ 再看一次");
  });

  // Acceptance 4.
  it("plays again from the start on 再看一次", () => {
    button.click();
    vi.advanceTimersByTime(2400);
    button.click();
    expect(pieces(svg)[1].getAttribute("transform")).toMatch(/^translate\(80 -55\)/);
    vi.advanceTimersByTime(2400);
    expect(pieces(svg)[1].getAttribute("transform")).toBe("translate(846 628)");
  });
});

const runPickExplain = () => new Function(readFileSync(PICK_EXPLAIN, "utf-8"))();
const live = () => document.querySelector("[data-pick-live]");
const folded = () => document.querySelector("[data-pick-explanations]");

describe("with 選外型", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    serverPage();
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  // Acceptance 6 and the spec's 配合「選外型」元件: the shape's steps are copied into the live
  // region; the copy has one working button, the folded original stays still and out of reach.
  for (const [order, run] of [
    ["the buttons are added first", () => (addMotionButtons(fakeWindow()), runPickExplain())],
    ["the shape was already shown", () => (runPickExplain(), addMotionButtons(fakeWindow()))],
  ]) {
    it(`plays a copied step, when ${order}`, () => {
      if (order.includes("already")) document.querySelector("input[type=radio]").checked = true;
      run();
      document.querySelector("input[type=radio]").click();
      expect(buttons(live())).toHaveLength(1);
      expect(folded().closest("[hidden]")).not.toBeNull();

      buttons(live())[0].click();
      const copy = live().querySelector("svg[data-motion]");
      expect(pieces(copy)[1].getAttribute("transform")).toMatch(/^translate\(80 -55\)/);
      vi.advanceTimersByTime(2400);
      expect(pieces(copy)[1].getAttribute("transform")).toBe("translate(846 628)");
      expect(words(buttons(live())[0])).toBe("再看一次");
      const original = folded().querySelector("svg[data-motion]");
      expect(pieces(original)[1].getAttribute("transform")).toBe("translate(846 628)");
      expect(arrowsGone(original)).toBe(false);
    });
  }
});

// Acceptance 5: a page with several steps that move; only the one pressed does.
it("moves only the drawing whose button was pressed", () => {
  vi.useFakeTimers();
  serverPage();
  const steps = document.querySelector("ol");
  steps.insertAdjacentHTML("beforeend", step("5. 塞好固定線", drawing(PUSH_IN, PUSH_IN_PIECES)));
  addMotionButtons(fakeWindow());
  const [first, second] = buttons();
  second.click();
  vi.advanceTimersByTime(1000);
  const still = first.previousElementSibling;
  expect(pieces(still)[1].getAttribute("transform")).toBe("translate(846 628)");
  expect(arrowsGone(still)).toBe(false);
  expect(words(first)).toBe("看動作");
  vi.useRealTimers();
  document.body.innerHTML = "";
});

// #522: the other kinds of motion in wear-motion-review.md's table.
describe("other motions", () => {
  const play = (motion, piecesHtml, ms) => {
    document.body.innerHTML = `<ol>${step("2. 轉出耳模", drawing(motion, piecesHtml))}</ol>`;
    addMotionButtons(fakeWindow());
    buttons()[0].click();
    vi.advanceTimersByTime(ms);
    return pieces(document.querySelector("svg"));
  };
  const numbers = (text) => text.match(/-?[\d.]+/g).map(Number);

  beforeEach(() => vi.useFakeTimers());

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  // Acceptance 3: taking out starts on the reviewed drawing and stays where it was pulled out.
  it("starts a taking out on the reviewed drawing and stops where it is pulled out", () => {
    const motion = { parts: [{ pieces: [0], pivot: [0, 0], keys: [[15, 0, 0, 0], [75, 150, -20, 0]] }], cues: [] };
    const [part] = play(motion, '<rect x="1" y="2" width="3" height="4"/>', 0);
    expect(part.getAttribute("transform")).toBeNull();
    vi.advanceTimersByTime(2400);
    expect(part.getAttribute("transform")).toBe("translate(150 -20) rotate(0 0 0)");
  });

  // 耳模轉進去: tilted 35° back about (890, 690) and off to the side, a tube's end with it; then
  // pushed in, then turned upright.
  const TWIST_IN = {
    parts: [{ pieces: [1], pivot: [890, 690], keys: [[15, 110, 40, -35], [50, 0, 0, -35], [80, 0, 0, 0]] }],
    lines: [{ pieces: [0], with: 0, points: [0] }],
    cues: [],
  };
  const TWIST_IN_PIECES = '<path d="M990 690C900 500 850 300 850 220"/><path d="M890 690h20"/>';

  it("turns a part about its pivot and takes a line's end with it", () => {
    const [tube, mould] = play(TWIST_IN, TWIST_IN_PIECES, 0);
    expect(mould.getAttribute("transform")).toBe("translate(110 40) rotate(-35 890 690)");
    // (990, 690) is 100 right of the pivot: turned 35° up it is (971.92, 632.64), then moved.
    const [x, y, ...rest] = numbers(tube.getAttribute("d"));
    expect(x).toBeCloseTo(1081.92, 1);
    expect(y).toBeCloseTo(672.64, 1);
    expect(rest).toEqual([900, 500, 850, 300, 850, 220]);
  });

  it("pushes in still tilted before turning upright", () => {
    const [, mould] = play(TWIST_IN, TWIST_IN_PIECES, 1200);
    expect(mould.getAttribute("transform")).toBe("translate(0 0) rotate(-35 890 690)");
    vi.advanceTimersByTime(1200);
    expect(mould.getAttribute("transform")).toBeNull();
  });

  // 塞好固定線: the line starts as another shape and becomes the reviewed one as the finger moves.
  it("changes a line from its start shape to the reviewed one with its part", () => {
    const motion = {
      parts: [{ pieces: [1], pivot: [0, 0], keys: [[15, 60, 110, 0], [75, 0, 0, 0]] }],
      shapes: [{ pieces: [0], with: 0, from: "M868 642C874 700 872 760 856 812" }],
      cues: [],
    };
    const [line] = play(motion, '<path d="M868 642C860 680 830 700 800 690"/><circle r="5"/>', 0);
    expect(line.getAttribute("d")).toBe("M868 642C874 700 872 760 856 812");
    vi.advanceTimersByTime(1080);
    const [, , x1, y1] = numbers(line.getAttribute("d"));
    expect(x1).toBeCloseTo(867, -0.5);
    expect(y1).toBeCloseTo(690, -0.5);
    vi.advanceTimersByTime(1320);
    expect(line.getAttribute("d")).toBe("M868 642C860 680 830 700 800 690");
  });
});
