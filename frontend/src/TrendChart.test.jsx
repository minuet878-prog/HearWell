import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TrendChart from "./TrendChart.jsx";

const LEVELS = [
  { code: "normal", text: "無/極輕微影響", max: 8 },
  { code: "mild_to_moderate", text: "輕度到中度影響", max: 24 },
  { code: "severe", text: "顯著影響", max: 40 },
];

function submission(
  id,
  date,
  total,
  text = "輕度到中度影響",
  questionnaire = { code: "hhie-s", name: "HHIE-S" },
  wearing = false,
) {
  return {
    id,
    // "2026-10-14" gets 14:30; "2026-10-14T16:00" keeps its own time.
    created_at: `${date.includes("T") ? date : `${date}T14:30`}:00+08:00`,
    questionnaire,
    wearing_hearing_aid: wearing,
    scores: { total, emotional: 0, social: 0 },
    level: { code: "mild_to_moderate", text },
  };
}

function mockApi({ results, next = null, levels = LEVELS, questionnaires = null }) {
  const responses = {
    "/api/submissions/": { next, previous: null, results },
    "/api/questionnaires/": questionnaires ?? [{ id: 1, code: "hhie-s", name: "HHIE-S", levels }],
  };
  globalThis.fetch = vi.fn((url) =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(responses[url]) }),
  );
}

const ERROR_TEXT = "趨勢圖暫時無法顯示，下方的紀錄不受影響。";

// Pixel y where a score of 0 belongs: the bottom of the plot area (Recharts clips lines to it).
function plotBottom(container) {
  const plot = container.querySelector(".recharts-wrapper clipPath rect");
  return Number(plot.getAttribute("y")) + Number(plot.getAttribute("height"));
}

function summaryLines(container) {
  return [...container.querySelectorAll(".trend-summary p")].map((p) =>
    p.textContent.replace(/\s+/g, " ").trim(),
  );
}

// Every point is drawn as a .trend-dot shape (circle, square or triangle) carrying its centre.
function dots(container) {
  return [...container.querySelectorAll(".recharts-line-dots .trend-dot")];
}

function dateTicks(container) {
  return [...container.querySelectorAll(".recharts-xAxis-tick-labels .recharts-cartesian-axis-tick-value")].map(
    (t) => t.textContent,
  );
}

// The corners of a line's path, as "x,y" strings.
function vertices(curve) {
  return [...(curve?.getAttribute("d") ?? "").matchAll(/[ML](-?[\d.]+),(-?[\d.]+)/g)].map(
    ([, x, y]) => `${Number(x)},${Number(y)}`,
  );
}

function lineParts(container, status) {
  // Recharts draws dots in a layer of their own, so they are found by their status, not their line.
  const curve = container.querySelector(`.trend-line-${status} .recharts-line-curve`);
  const points = [...container.querySelectorAll(`.trend-dot[data-status="${status}"]`)].map(
    (d) => `${Number(d.dataset.cx)},${Number(d.dataset.cy)}`,
  );
  return { curve, points };
}

function dotHeights(container) {
  return dots(container).map((d) => Number(d.dataset.cy));
}

// jsdom has no document.fonts; the chart waits for its ready promise.
function mockFonts(ready = Promise.resolve()) {
  Object.defineProperty(document, "fonts", { value: { ready }, configurable: true });
}

beforeEach(() => mockFonts());

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
  delete document.fonts;
});

describe("TrendChart", () => {
  // jsdom has no ResizeObserver, so ResponsiveContainer keeps its initialDimension and draws the chart.
  it("shows the summary, the title and a labelled band per level", async () => {
    mockApi({ results: [submission(2, "2026-10-14", 18), submission(1, "2026-09-01", 12)] });
    const { container } = render(<TrendChart code="hhie-s" />);
    await screen.findByText(/最近一次/);
    expect(summaryLines(container)).toEqual([
      "最近一次（2026/10/14，沒戴助聽器）",
      "18 分 輕度到中度影響",
      "比上一次沒戴助聽器（2026/09/01）增加 6 分。",
    ]);
    const bands = [...container.querySelectorAll(".recharts-reference-area-rect")];
    expect(bands.map((b) => [b.getAttribute("y1"), b.getAttribute("y2")])).toEqual([
      // Spec 4.4: halfway between levels, as HHIE-S totals are even.
      ["0", "9"],
      ["9", "25"],
      ["25", "40"],
    ]);
    expect(screen.getByRole("heading", { name: /HHIE-S/ })).toBeTruthy();
    for (const level of LEVELS) {
      expect(screen.getAllByText(level.text).length).toBeGreaterThan(0);
    }
  });

  it("draws a point for every submission, including a score of 0", async () => {
    mockApi({
      results: [
        submission(3, "2026-10-14", 0, "無/極輕微影響"),
        submission(2, "2026-09-01", 18),
        submission(1, "2026-08-01", 12),
      ],
    });
    const { container } = render(<TrendChart code="hhie-s" />);
    await screen.findByText(/最近一次/);
    expect(summaryLines(container).slice(1)).toEqual([
      "0 分 無/極輕微影響",
      "比上一次沒戴助聽器（2026/09/01）減少 18 分。",
    ]);
    const heights = dotHeights(container);
    expect(heights).toHaveLength(3);
    expect(heights[2]).toBe(plotBottom(container));
  });

  it("draws scores of 0 at the bottom even without levels", async () => {
    mockApi({ results: [submission(2, "2026-10-14", 0), submission(1, "2026-09-01", 0)], levels: [] });
    const { container } = render(<TrendChart code="hhie-s" />);
    await screen.findByText(/相同。/);
    const bottom = plotBottom(container);
    expect(dotHeights(container)).toEqual([bottom, bottom]);
  });

  it("draws the questionnaire it is given, even if another is newer", async () => {
    const hhiaS = { code: "hhia-s", name: "HHIA-S" };
    mockApi({
      results: [
        submission(3, "2026-10-14", 10, "輕度到中度影響", hhiaS),
        submission(2, "2026-09-01", 20),
        submission(1, "2026-08-01", 30, "輕度到中度影響", hhiaS),
      ],
      questionnaires: [
        { id: 1, code: "hhie-s", name: "HHIE-S", levels: LEVELS },
        { id: 2, code: "hhia-s", name: "HHIA-S", levels: [] },
      ],
    });
    const { container } = render(<TrendChart code="hhia-s" />);
    await screen.findByText(/最近一次/);
    expect(screen.getByRole("heading").textContent).toBe("HHIA-S 總分變化");
    expect(dotHeights(container)).toHaveLength(2);
    expect(container.querySelector(".recharts-reference-area")).toBeNull();
  });

  it("shows a shared day's records in one column, with their times in the tooltip", async () => {
    // Real data: more than one screening on the same day (spec 4.1, 4.3; acceptance 8, 16, 18).
    mockApi({
      results: [
        submission(4, "2026-10-14T16:00", 12),
        submission(3, "2026-10-14T15:00", 28, "顯著影響", undefined, true),
        submission(2, "2026-10-14T14:30", 40, "顯著影響"),
        submission(1, "2026-08-01", 0, "無/極輕微影響"),
      ],
    });
    const { container } = render(<TrendChart code="hhie-s" />);
    await screen.findByText(/最近一次/);
    expect(dateTicks(container)).toEqual(["2026/08/01", "2026/10/14"]);
    // The day's last unaided record (12) is drawn, not the earlier 40; the aided 28 shares its column.
    const unaided = dots(container).filter((d) => d.dataset.status === "unaided");
    const [aided] = dots(container).filter((d) => d.dataset.status === "aided");
    expect(unaided).toHaveLength(2);
    expect(aided.dataset.cx).toBe(unaided[1].dataset.cx);
    expect([...container.querySelectorAll(".trend-score")].map((t) => t.textContent)).not.toContain("40");
    const hover = async (dot) => {
      // jsdom puts the chart at (0, 0), so a dot's centre is also its client coordinates.
      fireEvent.mouseMove(container.querySelector(".recharts-wrapper"), {
        clientX: Number(dot.dataset.cx),
        clientY: Number(dot.dataset.cy),
      });
      // Recharts handles mouse moves on the next animation frame.
      await vi.waitFor(() => expect(container.querySelector(".recharts-tooltip-wrapper").textContent).not.toBe(""));
      return container.querySelector(".recharts-tooltip-wrapper").textContent;
    };
    await vi.waitFor(async () => {
      const shared = await hover(aided);
      expect(shared).toContain("2026/10/14");
      expect(shared).toContain("12 分，輕度到中度影響，助聽器：沒戴（16:00）");
      expect(shared).toContain("28 分，顯著影響，助聽器：有戴（15:00）");
    });
    await vi.waitFor(async () => {
      const single = await hover(unaided[0]);
      expect(single).toContain("2026/08/01");
      expect(single).not.toContain("（");
    });
  });

  it("draws the latest five days only (acceptance 17)", async () => {
    mockApi({
      results: [7, 6, 5, 4, 3, 2, 1].map((day) => submission(day, `2026-10-0${day}`, day * 2)),
    });
    const { container } = render(<TrendChart code="hhie-s" />);
    await screen.findByText(/最近一次/);
    expect(dateTicks(container)).toEqual(["2026/10/03", "2026/10/04", "2026/10/05", "2026/10/06", "2026/10/07"]);
    expect(dots(container)).toHaveLength(5);
  });

  it("draws no bands when the questionnaire has no levels", async () => {
    mockApi({ results: [submission(1, "2026-10-14", 18)], levels: [] });
    const { container } = render(<TrendChart code="hhie-s" />);
    await screen.findByText(/最近一次/);
    expect(container.querySelector(".recharts-line")).not.toBeNull();
    expect(container.querySelector(".recharts-reference-area")).toBeNull();
  });

  it("shows one point and how to see a change", async () => {
    mockApi({ results: [submission(1, "2026-10-14", 18)] });
    render(<TrendChart code="hhie-s" />);
    expect(await screen.findByText(/再做一次篩檢，就能看到分數的變化。/)).toBeTruthy();
  });

  it("renders nothing without submissions", async () => {
    mockApi({ results: [] });
    const { container } = render(<TrendChart code="hhie-s" />);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    await Promise.resolve();
    expect(container.textContent).toBe("");
  });

  it("only uses the first page (latest 20)", async () => {
    const results = Array.from({ length: 20 }, (_, i) => submission(20 - i, "2026-10-14", 10));
    mockApi({ results, next: "/api/submissions/?cursor=abc" });
    render(<TrendChart code="hhie-s" />);
    await screen.findByText(/最近一次/);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("shows the API's level text, not a recomputed one", async () => {
    mockApi({ results: [submission(1, "2026-10-14", 18, "假的分級")] });
    render(<TrendChart code="hhie-s" />);
    expect(await screen.findByText("假的分級")).toBeTruthy();
  });

  it("explains when the API returns an error", async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }));
    render(<TrendChart code="hhie-s" />);
    expect(await screen.findByText(ERROR_TEXT)).toBeTruthy();
  });

  describe("style (option A)", () => {
    const threePoints = () =>
      mockApi({
        results: [
          submission(3, "2026-10-14", 0, "無/極輕微影響"),
          submission(2, "2026-09-01", 18),
          submission(1, "2026-08-01", 12),
        ],
      });

    it("draws the line in the primary colour and makes the latest point bigger", async () => {
      threePoints();
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      expect(container.querySelector(".recharts-line-curve").getAttribute("stroke")).toBe("#1f4e8c");
      const all = dots(container);
      expect(all).toHaveLength(3);
      const [older, latest] = [all.slice(0, -1), all.at(-1)];
      for (const dot of older) {
        expect(Number(dot.dataset.size)).toBeLessThan(Number(latest.dataset.size));
      }
    });

    it("writes each score next to its point, including 0", async () => {
      threePoints();
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      const labels = [...container.querySelectorAll(".trend-score")].map((t) => t.textContent);
      expect(labels).toEqual(["12", "18", "0"]);
    });

    it("uses soft band colours, level-coloured labels and no y axis numbers", async () => {
      threePoints();
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      const bands = [...container.querySelectorAll(".recharts-reference-area-rect")];
      expect(bands.map((b) => b.getAttribute("fill"))).toEqual(["#e3f4ec", "#fff4d6", "#feece7"]);
      const bandLegend = within(container.querySelector(".trend-bands"));
      const labelColours = LEVELS.map((level) => bandLegend.getByText(level.text).style.color);
      expect(labelColours).toEqual(["rgb(20, 87, 60)", "rgb(112, 72, 0)", "rgb(143, 42, 18)"]);
      const ticks = [...container.querySelectorAll(".recharts-yAxis-tick-labels .recharts-cartesian-axis-tick-value")];
      expect(ticks).toEqual([]);
    });

    it("names the levels in a legend under the chart, top band first (phase9_ui_refresh_3_structure.md 4.5)", async () => {
      threePoints();
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      // Nothing written inside the plot, so no level name can cover a point.
      for (const level of LEVELS) {
        expect(container.querySelector(".recharts-wrapper").textContent).not.toContain(level.text);
      }
      const items = [...container.querySelectorAll(".trend-bands li")];
      expect(items.map((li) => li.textContent.trim())).toEqual(["顯著影響", "輕度到中度影響", "無/極輕微影響"]);
      const swatches = items.map((li) => li.querySelector(".trend-band-swatch").style.backgroundColor);
      expect(swatches).toEqual(["rgb(254, 236, 231)", "rgb(255, 244, 214)", "rgb(227, 244, 236)"]);
    });

    it("orders title, summary box and chart card, with the summary outside the card", async () => {
      threePoints();
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      const heading = screen.getByRole("heading");
      const summary = container.querySelector(".trend-summary");
      const card = container.querySelector(".card");
      expect(card.querySelector(".recharts-wrapper")).not.toBeNull();
      expect(card.contains(summary)).toBe(false);
      const follows = (a, b) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
      expect(follows(heading, summary)).toBe(true);
      expect(follows(summary, card)).toBe(true);
    });

    it("keeps the dates clear of the chart", async () => {
      threePoints();
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      const dates = [...container.querySelectorAll(".recharts-xAxis-tick-labels text")];
      expect(dates.length).toBeGreaterThan(0);
      for (const date of dates) {
        expect(Number(date.getAttribute("y")) - plotBottom(container)).toBeGreaterThanOrEqual(16);
      }
    });

    it("summary box: date, big score with level, then the change", async () => {
      mockApi({ results: [submission(2, "2026-10-14", 12), submission(1, "2026-09-01", 28)] });
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      expect(summaryLines(container)).toEqual([
        "最近一次（2026/10/14，沒戴助聽器）",
        "12 分 輕度到中度影響",
        "比上一次沒戴助聽器（2026/09/01）減少 16 分。",
      ]);
      expect(container.querySelector(".trend-summary-score strong").textContent).toBe("12 分");
    });

    it("summary box with one submission and a score of 0", async () => {
      mockApi({ results: [submission(1, "2026-10-14", 0, "無/極輕微影響")] });
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      expect(summaryLines(container)).toEqual([
        "最近一次（2026/10/14，沒戴助聽器）",
        "0 分 無/極輕微影響",
        "再做一次篩檢，就能看到分數的變化。",
      ]);
    });
  });

  describe("hearing aid status (spec 4b)", () => {
    const mixed = () =>
      mockApi({
        results: [
          submission(3, "2026-10-14", 14, "輕度到中度影響", undefined, null),
          submission(2, "2026-09-01", 12, "輕度到中度影響", undefined, true),
          submission(1, "2026-08-01", 10, "輕度到中度影響", undefined, false),
        ],
      });

    it("draws a filled circle, a hollow square and a hollow triangle", async () => {
      mixed();
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      const [unaided, aided, unrecorded] = dots(container);
      expect(unaided.tagName).toBe("circle");
      expect(unaided.getAttribute("fill")).toBe("#1f4e8c");
      expect(aided.tagName).toBe("rect");
      expect(aided.getAttribute("fill")).toBe("#fff");
      expect(unrecorded.tagName).toBe("polygon");
      expect(unrecorded.getAttribute("fill")).toBe("#fff");
      for (const dot of [aided, unrecorded]) expect(dot.getAttribute("stroke")).toBe("#1f4e8c");
    });

    it("explains the shapes in a legend, only for statuses that appear", async () => {
      mixed();
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      const legend = [...container.querySelectorAll(".trend-legend li")].map((li) => li.textContent.trim());
      expect(legend).toEqual(["沒戴助聽器", "有戴助聽器", "未記錄"]);
      cleanup();
      mockApi({ results: [submission(1, "2026-10-14", 10)] });
      const again = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      const only = [...again.container.querySelectorAll(".trend-legend li")].map((li) => li.textContent.trim());
      expect(only).toEqual(["沒戴助聽器"]);
    });

    it("names the status in the tooltip", async () => {
      mixed();
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      const expected = ["沒戴", "有戴", "未記錄"];
      expect(dots(container)).toHaveLength(3);
      for (const [i, dot] of dots(container).entries()) {
        fireEvent.mouseMove(container.querySelector(".recharts-wrapper"), {
          clientX: Number(dot.dataset.cx),
          clientY: Number(dot.dataset.cy),
        });
        await vi.waitFor(() =>
          expect(container.querySelector(".recharts-tooltip-wrapper").textContent).toContain(`助聽器：${expected[i]}`),
        );
      }
    });
  });

  describe("hearing aid lines (phase9_ui_refresh_2_data.md)", () => {
    // Acceptance 1: unaided 26, 24, 20 and aided 14, 10, oldest first.
    const fiveRecords = () =>
      mockApi({
        results: [
          submission(5, "2026-10-15T16:10", 10, "輕度到中度影響", undefined, true),
          submission(4, "2026-10-15T14:30", 20, "輕度到中度影響", undefined, false),
          submission(3, "2026-10-01", 14, "輕度到中度影響", undefined, true),
          submission(2, "2026-09-20", 24, "輕度到中度影響", undefined, false),
          submission(1, "2026-09-01", 26, "顯著影響", undefined, false),
        ],
      });

    it("joins only points of the same status (acceptance 1)", async () => {
      fiveRecords();
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      const unaided = lineParts(container, "unaided");
      const aided = lineParts(container, "aided");
      expect(unaided.points).toHaveLength(3);
      expect(aided.points).toHaveLength(2);
      // Every corner of each line is one of its own points, so no segment crosses statuses.
      expect(vertices(unaided.curve)).toEqual(unaided.points);
      expect(vertices(aided.curve)).toEqual(aided.points);
      // One unbroken line each: a record of the other status in between does not cut it.
      for (const { curve } of [unaided, aided]) {
        expect(curve.getAttribute("d").match(/M/g)).toHaveLength(1);
      }
    });

    it("draws aided dashed with hollow squares, unaided solid with filled circles (acceptance 2)", async () => {
      fiveRecords();
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      const unaided = lineParts(container, "unaided").curve;
      const aided = lineParts(container, "aided").curve;
      expect(unaided.getAttribute("stroke-dasharray")).toBeNull();
      expect(aided.getAttribute("stroke-dasharray")).toBeTruthy();
      const shapes = (status) =>
        [...container.querySelectorAll(`.trend-dot[data-status="${status}"]`)].map((d) => d.tagName);
      expect(shapes("unaided")).toEqual(["circle", "circle", "circle"]);
      expect(shapes("aided")).toEqual(["rect", "rect"]);
      const legend = [...container.querySelectorAll(".trend-legend li")];
      expect(legend.map((li) => li.textContent.trim())).toEqual(["沒戴助聽器", "有戴助聽器"]);
      expect(legend[0].querySelector("line").getAttribute("stroke-dasharray")).toBeNull();
      expect(legend[1].querySelector("line").getAttribute("stroke-dasharray")).toBeTruthy();
    });

    it("does not join unrecorded points (acceptance 3)", async () => {
      mockApi({
        results: [
          submission(3, "2026-10-14", 12, "輕度到中度影響", undefined, false),
          submission(2, "2026-09-01", 14, "輕度到中度影響", undefined, null),
          submission(1, "2026-08-01", 16, "輕度到中度影響", undefined, null),
        ],
      });
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      const unrecorded = lineParts(container, "unrecorded");
      expect(unrecorded.points).toHaveLength(2);
      expect(unrecorded.curve.getAttribute("stroke")).toBe("none");
      const shapes = [...container.querySelectorAll('.trend-dot[data-status="unrecorded"]')].map((d) => d.tagName);
      expect(shapes).toEqual(["polygon", "polygon"]);
    });

    it("draws one solid line when every record is unaided (acceptance 4)", async () => {
      mockApi({ results: [submission(2, "2026-10-14", 12), submission(1, "2026-09-01", 16)] });
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      const drawn = [...container.querySelectorAll(".recharts-line-curve")].filter(
        (c) => c.getAttribute("stroke") !== "none" && vertices(c).length > 0,
      );
      expect(drawn).toHaveLength(1);
      expect(drawn[0].closest(".trend-line-unaided")).not.toBeNull();
      const legend = [...container.querySelectorAll(".trend-legend li")].map((li) => li.textContent.trim());
      expect(legend).toEqual(["沒戴助聽器"]);
    });

    it("compares the summary with the same status only (acceptance 5)", async () => {
      fiveRecords();
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      expect(summaryLines(container)).toEqual([
        "最近一次（2026/10/15，有戴助聽器）",
        "10 分 輕度到中度影響",
        "比上一次有戴助聽器（2026/10/01）減少 4 分。",
      ]);
    });

    it("puts each score inside its own level band (acceptance 10)", async () => {
      mockApi({
        results: [26, 24, 10, 8].map((total, i) => submission(4 - i, `2026-10-0${4 - i}`, total)),
      });
      const { container } = render(<TrendChart code="hhie-s" />);
      await screen.findByText(/最近一次/);
      const bands = [...container.querySelectorAll(".recharts-reference-area-rect")].map((b) => ({
        top: Number(b.getAttribute("y")),
        bottom: Number(b.getAttribute("y")) + Number(b.getAttribute("height")),
      }));
      const [normal, mild, severe] = bands;
      // Oldest first: 8, 10, 24, 26.
      const [eight, ten, twentyFour, twentySix] = dotHeights(container);
      const inside = (y, band) => y > band.top && y < band.bottom;
      expect(inside(eight, normal)).toBe(true);
      expect(inside(ten, mild)).toBe(true);
      expect(inside(twentyFour, mild)).toBe(true);
      expect(inside(twentySix, severe)).toBe(true);
    });

    it("says which way is better under the title (acceptance 13)", async () => {
      fiveRecords();
      render(<TrendChart code="hhie-s" />);
      expect(await screen.findByText("分數越低，聽力對生活的影響越小。")).toBeTruthy();
    });
  });

  // Recharts measures each date once and keeps the width: measured in the fallback font, the
  // first date sticks out of the chart once Noto Sans TC arrives.
  it("waits for the web font before drawing the dates", async () => {
    let fontsLoaded;
    mockFonts(new Promise((resolve) => (fontsLoaded = resolve)));
    mockApi({ results: [submission(2, "2026-10-14", 18), submission(1, "2026-09-01", 12)] });
    const { container } = render(<TrendChart code="hhie-s" />);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    await act(() => Promise.resolve());
    expect(dateTicks(container)).toEqual([]);
    await act(() => fontsLoaded());
    expect(dateTicks(container)).toEqual(["2026/09/01", "2026/10/14"]);
  });

  it("draws anyway after 3 seconds if the web font never arrives", async () => {
    vi.useFakeTimers();
    mockFonts(new Promise(() => {}));
    mockApi({ results: [submission(2, "2026-10-14", 18), submission(1, "2026-09-01", 12)] });
    const { container } = render(<TrendChart code="hhie-s" />);
    await act(() => vi.advanceTimersByTimeAsync(2999));
    expect(dateTicks(container)).toEqual([]);
    await act(() => vi.advanceTimersByTimeAsync(1));
    expect(dateTicks(container)).toEqual(["2026/09/01", "2026/10/14"]);
  });

  it("explains when the network fails", async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    render(<TrendChart code="hhie-s" />);
    expect(await screen.findByText(ERROR_TEXT)).toBeTruthy();
  });
});
