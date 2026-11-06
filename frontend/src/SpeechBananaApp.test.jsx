import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it } from "vitest";

import SpeechBananaApp from "./SpeechBananaApp.jsx";
import { CHART, x, y } from "./audiogram.js";

// jsdom has no layout: make one screen pixel equal one chart unit.
beforeEach(() => {
  SVGElement.prototype.getBoundingClientRect = () => ({ left: 0, top: 0, width: CHART.width, height: CHART.height });
});
afterEach(cleanup);

const HEARD = { status: "heard", text: "可能聽得到" };
const HARD = { status: "hard", text: "可能不容易聽到" };
const NO_MARK = { status: "no_mark", text: "這個頻率沒有標記，無法估計" };
const air = (ear, frequency, db) => ({ ear, conduction: "air", frequency, db, no_response: false, masked: false });

const DATA = {
  banana: { top: [[281, 36], [1000, 40], [9580, 21.5]], bottom: [[10660, 26], [1000, 56], [308, 43.5]] },
  groups: [
    { rows: ["ㄩㄧㄨ", "ㄝㄜㄛㄦ"], frequency: 460, db: 44, description: "母音的低音部分", examples: "ㄧ「一」、ㄨ「五」、ㄩ「魚」" },
    { rows: ["ㄚㄨㄛ", "ㄚㄜㄦ"], frequency: 1200, db: 46, description: "母音", examples: "ㄚ「阿」、ㄛ「喔」、ㄜ「鵝」" },
    { rows: ["ㄝㄩㄇㄖ", "ㄧㄋㄌ"], frequency: 2400, db: 48, description: "鼻音、ㄌ 和母音的高音部分", examples: "ㄇ「媽」、ㄋ「你」、ㄌ「老」" },
    { rows: ["ㄏㄅㄉㄍ", "ㄆㄎㄊ"], frequency: 3300, db: 44, description: "短促的子音", examples: "ㄅ「爸」、ㄉ「大」、ㄍ「哥」、ㄎ「看」" },
    { rows: ["ㄈㄐㄑㄓ", "ㄔㄒㄕ"], frequency: 5500, db: 39, description: "高音的子音", examples: "ㄕ「是」、ㄑ「七」、ㄒ「西」、ㄔ「吃」" },
    { rows: ["ㄗㄙㄘ"], frequency: 6600, db: 35, description: "最高音的子音", examples: "ㄙ「四」、ㄘ「菜」、ㄗ「字」" },
  ],
  ears: [
    { ear: "right", label: "右耳", marks: [air("right", 1000, 30), air("right", 2000, 50)], results: [NO_MARK, HEARD, NO_MARK, NO_MARK, HARD, NO_MARK], stretches: [] },
    { ear: "left", label: "左耳", marks: [air("left", 500, 70), air("left", 8000, 80)], results: [HARD, HARD, HARD, HARD, HEARD, HARD], stretches: [] },
  ],
};

const box = (container, group) => container.querySelector(`[data-group="${group}"]`);
const pick = (name) => fireEvent.click(screen.getByRole("button", { name }));

it("opens with nothing picked and the hint in the announced result area", () => {
  const { container } = render(<SpeechBananaApp data={DATA} />);
  expect(screen.getByRole("status").textContent).toBe("點圖上的注音，看那一群。");
  expect(container.querySelector('[data-selected="true"]')).toBeNull();
  expect(screen.getAllByRole("button").filter((b) => b.getAttribute("aria-pressed") === "true")).toHaveLength(0);
});

it("draws the banana and one box per group, tied to a dot at its representative point", () => {
  const { container } = render(<SpeechBananaApp data={DATA} />);
  expect(container.querySelector(".speech-banana-area").getAttribute("points")).toBe(
    [[281, 36], [1000, 40], [9580, 21.5], [10660, 26], [1000, 56], [308, 43.5]].map(([f, db]) => `${x(f)},${y(db)}`).join(" "),
  );
  DATA.groups.forEach((group, i) => {
    const drawn = box(container, i + 1);
    expect(Number(drawn.querySelector("circle").getAttribute("cx"))).toBe(x(group.frequency));
    expect(Number(drawn.querySelector("circle").getAttribute("cy"))).toBe(y(group.db));
    expect([...drawn.querySelectorAll("text")].map((t) => t.textContent)).toEqual(group.rows);
    // The thin line starts on the dot and ends in the box's centre.
    const line = drawn.querySelector("line");
    const rect = drawn.querySelector("rect");
    expect(Number(line.getAttribute("x1"))).toBe(x(group.frequency));
    expect(Number(line.getAttribute("x2"))).toBe(Number(rect.getAttribute("x")) + Number(rect.getAttribute("width")) / 2);
    expect(Number(line.getAttribute("y2"))).toBe(Number(rect.getAttribute("y")) + Number(rect.getAttribute("height")) / 2);
  });
});

it("draws only the right ear's marks, with a text alternative for the chart", () => {
  const { container } = render(<SpeechBananaApp data={DATA} />);
  expect(container.querySelector('[data-point="right-air-1000"]')).not.toBeNull();
  expect(container.querySelector('[data-point="left-air-500"]')).toBeNull();
  const chart = screen.getByRole("img");
  expect(chart.getAttribute("aria-label")).toContain("語言香蕉區");
  expect(chart.getAttribute("aria-label")).toContain("右耳");
  expect(chart.getAttribute("aria-label")).toContain("用清單選");
});

it("picking from the list darkens that box and writes the group and both ears", () => {
  const { container } = render(<SpeechBananaApp data={DATA} />);
  pick("ㄈㄐㄑㄓㄔㄒㄕ");
  const result = within(screen.getByRole("status"));
  expect(screen.getByRole("status").textContent).not.toContain("點圖上的注音");
  result.getByText("ㄈㄐㄑㄓㄔㄒㄕ");
  result.getByText("高音的子音");
  result.getByText("ㄕ「是」、ㄑ「七」、ㄒ「西」、ㄔ「吃」");
  expect(screen.getByRole("status").textContent).toContain("右耳：可能不容易聽到");
  expect(screen.getByRole("status").textContent).toContain("左耳：可能聽得到");
  expect(box(container, 5).getAttribute("data-selected")).toBe("true");
  expect(box(container, 5).querySelector("rect").getAttribute("fill")).toBe("#1f4e8c");
  expect(box(container, 5).querySelector("text").getAttribute("fill")).toBe("#fff");
  expect(box(container, 1).querySelector("rect").getAttribute("fill")).toBe("#fff");
  expect(screen.getByRole("button", { name: "ㄈㄐㄑㄓㄔㄒㄕ" }).getAttribute("aria-pressed")).toBe("true");
  // Picking another moves it, and each ear's sentence follows the group.
  pick("ㄚㄨㄛㄚㄜㄦ");
  expect(box(container, 5).getAttribute("data-selected")).toBe("false");
  expect(box(container, 2).getAttribute("data-selected")).toBe("true");
  expect(screen.getByRole("status").textContent).toContain("右耳：可能聽得到");
  expect(screen.getByRole("status").textContent).toContain("左耳：可能不容易聽到");
});

it("the list has one button per group under its title", () => {
  render(<SpeechBananaApp data={DATA} />);
  expect(screen.getByText("用清單選").tagName).toBe("SUMMARY");
  expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
    "ㄩㄧㄨㄝㄜㄛㄦ",
    "ㄚㄨㄛㄚㄜㄦ",
    "ㄝㄩㄇㄖㄧㄋㄌ",
    "ㄏㄅㄉㄍㄆㄎㄊ",
    "ㄈㄐㄑㄓㄔㄒㄕ",
    "ㄗㄙㄘ",
  ]);
});

const tap = (at, on = screen.getByRole("img")) => fireEvent.click(on, { clientX: at[0], clientY: at[1] });

it("tapping empty space picks the group whose box centre is nearest", () => {
  const { container } = render(<SpeechBananaApp data={DATA} />);
  // Box 5's centre is 46 away, box 6's 58.
  tap([285, 170]);
  expect(box(container, 5).getAttribute("data-selected")).toBe("true");
  expect(box(container, 5).querySelector("rect").getAttribute("fill")).toBe("#1f4e8c");
  expect(screen.getByRole("status").textContent).toContain("高音的子音");
  expect(screen.getByRole("status").textContent).toContain("右耳：可能不容易聽到");
  expect(screen.getByRole("status").textContent).toContain("左耳：可能聽得到");
  expect(screen.getByRole("button", { name: "ㄈㄐㄑㄓㄔㄒㄕ" }).getAttribute("aria-pressed")).toBe("true");
});

it("distance runs to the box, not to the dot it is tied to", () => {
  const { container } = render(<SpeechBananaApp data={DATA} />);
  // 10 from group 5's dot and 13 from group 6's, but 65 from box 5's centre and 39 from box 6's.
  tap([285, 150]);
  expect(box(container, 6).getAttribute("data-selected")).toBe("true");
  expect(box(container, 5).getAttribute("data-selected")).toBe("false");
});

it("a tap outside the frame still picks the nearest group, and a later tap moves the pick", () => {
  const { container } = render(<SpeechBananaApp data={DATA} />);
  tap([2, 378]);
  expect(box(container, 1).getAttribute("data-selected")).toBe("true");
  tap([318, 2]);
  expect(box(container, 1).getAttribute("data-selected")).toBe("false");
  expect(box(container, 6).getAttribute("data-selected")).toBe("true");
});

it("a tap anywhere on a box picks that box, right to its corners", () => {
  const { container } = render(<SpeechBananaApp data={DATA} />);
  DATA.groups.forEach((_, i) => {
    const rect = box(container, i + 1).querySelector("rect");
    const [left, top] = [Number(rect.getAttribute("x")), Number(rect.getAttribute("y"))];
    const [right, bottom] = [left + Number(rect.getAttribute("width")), top + Number(rect.getAttribute("height"))];
    [[left, top], [right, top], [left, bottom], [right, bottom]].forEach((corner) => {
      tap(corner, rect);
      expect(container.querySelector('[data-selected="true"]').getAttribute("data-group"), `group ${i + 1} at ${corner}`).toBe(String(i + 1));
    });
  });
});

it("picking by tap and from the list draw exactly the same", () => {
  const byList = render(<SpeechBananaApp data={DATA} />);
  pick("ㄈㄐㄑㄓㄔㄒㄕ");
  const listed = byList.container.innerHTML;
  cleanup();
  const byTap = render(<SpeechBananaApp data={DATA} />);
  tap([285, 170]);
  expect(byTap.container.innerHTML).toBe(listed);
});

it("the chart stays a picture: keyboards and screen readers keep using the list", () => {
  render(<SpeechBananaApp data={DATA} />);
  const chart = screen.getByRole("img");
  expect(chart.tagName.toLowerCase()).toBe("svg");
  expect(chart.hasAttribute("tabindex")).toBe(false);
  expect(chart.querySelectorAll("[tabindex], [role='button'], a, button")).toHaveLength(0);
});
