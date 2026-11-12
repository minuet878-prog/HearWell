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
  expect(container.querySelector('details [aria-pressed="true"]')).toBeNull();
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

// A worked example for the ears: every status is the server's, stretches included.
const BROKEN = { status: "broken", text: "無法確定（聽力線在這裡因無反應斷開）" };
const JUDGED = {
  ...DATA,
  ears: [
    {
      ear: "right",
      label: "右耳",
      marks: [air("right", 1000, 30), air("right", 2000, 50)],
      results: [NO_MARK, HEARD, BROKEN, NO_MARK, HARD, NO_MARK],
      stretches: [[[1000, 30], [2000, 50]]],
    },
    {
      ear: "left",
      label: "左耳",
      marks: [air("left", 500, 70), air("left", 1000, 75), { ...air("left", 2000, 120), no_response: true }, air("left", 4000, 80), air("left", 8000, 90)],
      results: [HARD, HARD, BROKEN, HEARD, HARD, HEARD],
      stretches: [[[500, 70], [1000, 75]], [[4000, 80], [8000, 90]]],
    },
  ],
};
const earButton = (name) => within(screen.getByRole("group", { name: "選耳朵" })).getByRole("button", { name });
const after = (first, second) => Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING);

it("draws the marks and the line over the boxes, on a white edge that shows on a dark box", () => {
  const { container } = render(<SpeechBananaApp data={JUDGED} />);
  const lastBox = box(container, 6);
  expect(after(lastBox, container.querySelector(".air-line-right"))).toBe(true);
  expect(after(lastBox, container.querySelector('[data-point="right-air-1000"]'))).toBe(true);
  // The edge sits between the boxes and the marks; the left ear's blue is the picked box's colour.
  const edges = container.querySelector(".speech-banana-mark-edges");
  expect(after(lastBox, edges)).toBe(true);
  expect(after(edges, container.querySelector(".air-line-right"))).toBe(true);
  expect([...edges.querySelectorAll("circle")].map((c) => [c.getAttribute("cx"), c.getAttribute("cy"), c.getAttribute("fill")])).toEqual([
    [String(x(1000)), String(y(30)), "#fff"],
    [String(x(2000)), String(y(50)), "#fff"],
  ]);
  expect(edges.querySelector("polyline").getAttribute("points")).toBe(`${x(1000)},${y(30)} ${x(2000)},${y(50)}`);
  expect(edges.querySelector("polyline").getAttribute("stroke")).toBe("#fff");
});

const chartLabel = (name) => `聽力圖，畫出語言香蕉區、六群注音和${name}的標記。要看每一群的結果，請用圖下的「用清單選」。`;

it("opens on the right ear and says so to a screen reader", () => {
  render(<SpeechBananaApp data={JUDGED} />);
  expect(earButton("右耳").getAttribute("aria-pressed")).toBe("true");
  expect(earButton("左耳").getAttribute("aria-pressed")).toBe("false");
  expect(screen.getByRole("img").getAttribute("aria-label")).toBe(chartLabel("右耳"));
});

it("switching ears changes the marks and the chart's words, keeps the group and both ears' sentences", () => {
  const { container } = render(<SpeechBananaApp data={JUDGED} />);
  pick("ㄈㄐㄑㄓㄔㄒㄕ");
  const before = screen.getByRole("status").textContent;
  fireEvent.click(earButton("左耳"));
  expect(earButton("左耳").getAttribute("aria-pressed")).toBe("true");
  expect(earButton("右耳").getAttribute("aria-pressed")).toBe("false");
  expect(screen.getByRole("img").getAttribute("aria-label")).toBe(chartLabel("左耳"));
  expect(container.querySelector('[data-point="left-air-500"]')).not.toBeNull();
  expect(container.querySelector('[data-point="right-air-1000"]')).toBeNull();
  expect(box(container, 5).getAttribute("data-selected")).toBe("true");
  expect(screen.getByRole("status").textContent).toBe(before);
  expect(before).toContain("右耳：可能不容易聽到");
  expect(before).toContain("左耳：可能不容易聽到");
  // The white edge follows the ear too.
  expect(container.querySelectorAll(".speech-banana-mark-edges circle")).toHaveLength(5);
  fireEvent.click(earButton("右耳"));
  expect(container.querySelector('[data-point="right-air-1000"]')).not.toBeNull();
  expect(screen.getByRole("img").getAttribute("aria-label")).toBe(chartLabel("右耳"));
});

const dash = (container, group) => box(container, group).querySelector("rect").getAttribute("stroke-dasharray");

it("only the groups the server calls hard get a dashed box, and the same blue, for the ear shown", () => {
  const { container } = render(<SpeechBananaApp data={JUDGED} />);
  // Right ear: no mark, heard, broken, no mark, hard, no mark.
  expect([1, 2, 3, 4, 5, 6].map((g) => Boolean(dash(container, g)))).toEqual([false, false, false, false, true, false]);
  const strokes = () => [1, 2, 3, 4, 5, 6].map((g) => box(container, g).querySelector("rect").getAttribute("stroke"));
  expect(new Set(strokes()).size).toBe(1);
  fireEvent.click(earButton("左耳"));
  // Left ear: hard, hard, broken, heard, hard, heard.
  expect([1, 2, 3, 4, 5, 6].map((g) => Boolean(dash(container, g)))).toEqual([true, true, false, false, true, false]);
  expect(new Set(strokes()).size).toBe(1);
});

it("a picked box is solid dark blue: only a hard box that is not picked is dashed", () => {
  const { container } = render(<SpeechBananaApp data={JUDGED} />);
  const rect = (group) => box(container, group).querySelector("rect");
  // Group 5 is hard in the right ear. Picked, its dashes go; picked away from, they come back.
  expect(dash(container, 5)).toBe("4 3");
  pick("ㄈㄐㄑㄓㄔㄒㄕ");
  expect(dash(container, 5)).toBeNull();
  expect(rect(5).getAttribute("fill")).toBe("#1f4e8c");
  expect(rect(5).getAttribute("stroke")).toBe("#1f4e8c");
  // Group 2 is heard: solid whether picked or not.
  pick("ㄚㄨㄛㄚㄜㄦ");
  expect(dash(container, 5)).toBe("4 3");
  expect(dash(container, 2)).toBeNull();
  // Group 1 is hard only in the left ear, where the same rule holds.
  fireEvent.click(earButton("左耳"));
  expect(dash(container, 1)).toBe("4 3");
  pick("ㄩㄧㄨㄝㄜㄛㄦ");
  expect(dash(container, 1)).toBeNull();
});

it("draws no green normal range, so the only colour band on the chart is the banana (#436)", () => {
  const { container } = render(<SpeechBananaApp data={JUDGED} />);
  expect(container.querySelector('rect[fill="#e9f5ec"]')).toBeNull();
  // The first thing drawn is the grid, with nothing under it.
  expect(container.querySelector("svg").firstElementChild.tagName.toLowerCase()).toBe("g");
});

const hatches = (container) => [...container.querySelectorAll(".speech-banana-hatch")];

it("hatches one piece per stretch, from its line up to the chart's top, kept inside the banana", () => {
  const { container } = render(<SpeechBananaApp data={JUDGED} />);
  const up = (frequency) => `${x(frequency)},${y(-10)}`;
  expect(hatches(container).map((h) => h.getAttribute("points"))).toEqual([
    `${up(1000)} ${x(1000)},${y(30)} ${x(2000)},${y(50)} ${up(2000)}`,
  ]);
  const banana = container.querySelector(".speech-banana-area").getAttribute("points");
  const clip = hatches(container)[0].getAttribute("clip-path").match(/url\(#(.+)\)/)[1];
  expect(container.querySelector(`clipPath[id="${clip}"] polygon`).getAttribute("points")).toBe(banana);
  // By lines rather than a colour: the fill is a pattern of grey lines.
  const fill = hatches(container)[0].getAttribute("fill").match(/url\(#(.+)\)/)[1];
  expect(container.querySelector(`pattern[id="${fill}"] line`).getAttribute("stroke")).toBe("#5a6371");
  fireEvent.click(earButton("左耳"));
  // The left ear's no-response mark splits it in two, and neither piece reaches it.
  expect(hatches(container).map((h) => h.getAttribute("points"))).toEqual([
    `${up(500)} ${x(500)},${y(70)} ${x(1000)},${y(75)} ${up(1000)}`,
    `${up(4000)} ${x(4000)},${y(80)} ${x(8000)},${y(90)} ${up(8000)}`,
  ]);
});

it("hatches nothing without a stretch, whatever the results say", () => {
  const { container } = render(<SpeechBananaApp data={DATA} />);
  expect(hatches(container)).toHaveLength(0);
});

it("explains the yellow, the hatching and the dashes in the reviewed words", () => {
  render(<SpeechBananaApp data={DATA} />);
  screen.getByText("黃色是語言香蕉區，是說話聲通常落在的範圍。斜線蓋住的部分和虛線框的注音，這一耳沒戴助聽器時可能不容易聽到。");
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
  const { container } = render(<SpeechBananaApp data={DATA} />);
  expect(screen.getByText("用清單選").tagName).toBe("SUMMARY");
  expect(within(container.querySelector("details")).getAllByRole("button").map((b) => b.textContent)).toEqual([
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
