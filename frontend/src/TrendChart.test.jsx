import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TrendChart from "./TrendChart.jsx";

const LEVELS = [
  { code: "normal", text: "無/極輕微影響", max: 8, color: "normal", shade: "pale" },
  { code: "mild_to_moderate", text: "輕度到中度影響", max: 24, color: "mild_to_moderate", shade: "pale" },
  { code: "severe", text: "顯著影響", max: 40, color: "severe", shade: "pale" },
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

const LOADING_TEXT = "趨勢圖載入中…";
const ERROR_TEXT = "趨勢圖暫時無法顯示，下方的紀錄不受影響。";

// Pixel y where a score of 0 belongs: the bottom of the plot area (Recharts clips lines to it).
function plotBottom(container) {
  const plot = container.querySelector(".recharts-wrapper clipPath rect");
  return Number(plot.getAttribute("y")) + Number(plot.getAttribute("height"));
}

// The title, summary box and legends are drawn by Django (trend_chart.html); this draws the chart.
async function chartDrawn(container) {
  await vi.waitFor(() => expect(container.querySelector(".recharts-wrapper")).not.toBeNull());
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
  it("says it is loading until the data arrives", async () => {
    globalThis.fetch = vi.fn(() => new Promise(() => {}));
    const { container } = render(<TrendChart code="hhie-s" />);
    const message = container.querySelector(".trend-plot-message");
    expect(message.textContent).toBe(LOADING_TEXT);
    // Screen readers skip it, as they skip the chart: the summary box says the same in text.
    expect(message.getAttribute("aria-hidden")).toBe("true");
    // B1 (ADR 0027): the sliding track under the text.
    expect(message.classList.contains("loading-message")).toBe(true);
  });

  it("hides the chart from screen readers", async () => {
    mockApi({ results: [submission(1, "2026-10-14", 18)] });
    const { container } = render(<TrendChart code="hhie-s" />);
    await chartDrawn(container);
    expect(container.querySelector(".recharts-wrapper").closest('[aria-hidden="true"]')).not.toBeNull();
    expect(container.querySelector(".trend-plot-message")).toBeNull();
  });

  it("draws a band per level", async () => {
    mockApi({ results: [submission(2, "2026-10-14", 18), submission(1, "2026-09-01", 12)] });
    const { container } = render(<TrendChart code="hhie-s" />);
    await chartDrawn(container);
    const bands = [...container.querySelectorAll(".recharts-reference-area-rect")];
    expect(bands.map((b) => [b.getAttribute("y1"), b.getAttribute("y2")])).toEqual([
      // Spec 4.4: halfway between levels, as HHIE-S totals are even.
      ["0", "9"],
      ["9", "25"],
      ["25", "40"],
    ]);
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
    await chartDrawn(container);
    const heights = dotHeights(container);
    expect(heights).toHaveLength(3);
    expect(heights[2]).toBe(plotBottom(container));
  });

  it("draws scores of 0 at the bottom even without levels", async () => {
    mockApi({ results: [submission(2, "2026-10-14", 0), submission(1, "2026-09-01", 0)], levels: [] });
    const { container } = render(<TrendChart code="hhie-s" />);
    await chartDrawn(container);
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
    await chartDrawn(container);
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
    await chartDrawn(container);
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
    await chartDrawn(container);
    expect(dateTicks(container)).toEqual(["2026/10/03", "2026/10/04", "2026/10/05", "2026/10/06", "2026/10/07"]);
    expect(dots(container)).toHaveLength(5);
  });

  it("draws no bands when the questionnaire has no levels", async () => {
    mockApi({ results: [submission(1, "2026-10-14", 18)], levels: [] });
    const { container } = render(<TrendChart code="hhie-s" />);
    await chartDrawn(container);
    expect(container.querySelector(".recharts-line")).not.toBeNull();
    expect(container.querySelector(".recharts-reference-area")).toBeNull();
  });

  it("renders nothing without submissions", async () => {
    mockApi({ results: [] });
    const { container } = render(<TrendChart code="hhie-s" />);
    await vi.waitFor(() => expect(container.textContent).toBe(""));
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("only uses the first page (latest 20)", async () => {
    const results = Array.from({ length: 20 }, (_, i) => submission(20 - i, "2026-10-14", 10));
    mockApi({ results, next: "/api/submissions/?cursor=abc" });
    const { container } = render(<TrendChart code="hhie-s" />);
    await chartDrawn(container);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("explains when the API returns an error, also to screen readers", async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }));
    render(<TrendChart code="hhie-s" />);
    const message = await screen.findByText(ERROR_TEXT);
    expect(message.closest("[aria-hidden]")).toBeNull();
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
      await chartDrawn(container);
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
      await chartDrawn(container);
      const labels = [...container.querySelectorAll(".trend-score")].map((t) => t.textContent);
      expect(labels).toEqual(["12", "18", "0"]);
    });

    it("uses soft band colours and no y axis numbers", async () => {
      threePoints();
      const { container } = render(<TrendChart code="hhie-s" />);
      await chartDrawn(container);
      const bands = [...container.querySelectorAll(".recharts-reference-area-rect")];
      expect(bands.map((b) => b.getAttribute("fill"))).toEqual(["#e3f4ec", "#fff4d6", "#feece7"]);
      const ticks = [...container.querySelectorAll(".recharts-yAxis-tick-labels .recharts-cartesian-axis-tick-value")];
      expect(ticks).toEqual([]);
    });

    it("fills each band by its level's colour, not its code (#210)", async () => {
      mockApi({
        results: [submission(1, "2026-10-14", 18)],
        levels: [
          { code: "none", text: "無", max: 16, color: "normal", shade: "pale" },
          { code: "mild", text: "輕度", max: 36, color: "mild_to_moderate", shade: "pale" },
          { code: "moderate", text: "中度", max: 56, color: "mild_to_moderate", shade: "deep" },
          { code: "severe", text: "重度", max: 100, color: "severe", shade: "pale" },
        ],
      });
      const { container } = render(<TrendChart code="hhie-s" />);
      await chartDrawn(container);
      const bands = [...container.querySelectorAll(".recharts-reference-area-rect")];
      expect(bands.map((b) => b.getAttribute("fill"))).toEqual(["#e3f4ec", "#fff4d6", "#f9dd96", "#feece7"]);
    });

    it("fills the deeper shade where the API says so, white lines between bands (THI's five levels)", async () => {
      mockApi({
        results: [submission(1, "2026-10-14", 48)],
        levels: [
          { code: "none", text: "無", max: 16, color: "normal", shade: "pale" },
          { code: "mild", text: "輕度", max: 36, color: "mild_to_moderate", shade: "pale" },
          { code: "moderate", text: "中度", max: 56, color: "mild_to_moderate", shade: "deep" },
          { code: "severe", text: "重度", max: 76, color: "severe", shade: "pale" },
          { code: "catastrophic", text: "極重度", max: 100, color: "severe", shade: "deep" },
        ],
      });
      const { container } = render(<TrendChart code="hhie-s" />);
      await chartDrawn(container);
      const bands = [...container.querySelectorAll(".recharts-reference-area-rect")];
      expect(bands.map((b) => b.getAttribute("fill"))).toEqual([
        "#e3f4ec",
        "#fff4d6",
        "#f9dd96",
        "#feece7",
        "#f6c3b3",
      ]);
      for (const band of bands) {
        expect(band.getAttribute("stroke")).toBe("#fff");
        expect(band.getAttribute("stroke-width")).toBe("2");
      }
    });

    it("writes no level name inside the plot (phase9_ui_refresh_3_structure.md 4.5)", async () => {
      threePoints();
      const { container } = render(<TrendChart code="hhie-s" />);
      await chartDrawn(container);
      // Nothing written inside the plot, so no level name can cover a point.
      for (const level of LEVELS) {
        expect(container.querySelector(".recharts-wrapper").textContent).not.toContain(level.text);
      }
    });

    it("keeps the dates clear of the chart", async () => {
      threePoints();
      const { container } = render(<TrendChart code="hhie-s" />);
      await chartDrawn(container);
      const dates = [...container.querySelectorAll(".recharts-xAxis-tick-labels text")];
      expect(dates.length).toBeGreaterThan(0);
      for (const date of dates) {
        expect(Number(date.getAttribute("y")) - plotBottom(container)).toBeGreaterThanOrEqual(16);
      }
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
      await chartDrawn(container);
      const [unaided, aided, unrecorded] = dots(container);
      expect(unaided.tagName).toBe("circle");
      expect(unaided.getAttribute("fill")).toBe("#1f4e8c");
      expect(aided.tagName).toBe("rect");
      expect(aided.getAttribute("fill")).toBe("#fff");
      expect(unrecorded.tagName).toBe("polygon");
      expect(unrecorded.getAttribute("fill")).toBe("#fff");
      for (const dot of [aided, unrecorded]) expect(dot.getAttribute("stroke")).toBe("#1f4e8c");
    });

    it("names the status in the tooltip", async () => {
      mixed();
      const { container } = render(<TrendChart code="hhie-s" />);
      await chartDrawn(container);
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
      await chartDrawn(container);
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
      await chartDrawn(container);
      const unaided = lineParts(container, "unaided").curve;
      const aided = lineParts(container, "aided").curve;
      expect(unaided.getAttribute("stroke-dasharray")).toBeNull();
      expect(aided.getAttribute("stroke-dasharray")).toBeTruthy();
      const shapes = (status) =>
        [...container.querySelectorAll(`.trend-dot[data-status="${status}"]`)].map((d) => d.tagName);
      expect(shapes("unaided")).toEqual(["circle", "circle", "circle"]);
      expect(shapes("aided")).toEqual(["rect", "rect"]);
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
      await chartDrawn(container);
      const unrecorded = lineParts(container, "unrecorded");
      expect(unrecorded.points).toHaveLength(2);
      expect(unrecorded.curve.getAttribute("stroke")).toBe("none");
      const shapes = [...container.querySelectorAll('.trend-dot[data-status="unrecorded"]')].map((d) => d.tagName);
      expect(shapes).toEqual(["polygon", "polygon"]);
    });

    it("draws one solid line when every record is unaided (acceptance 4)", async () => {
      mockApi({ results: [submission(2, "2026-10-14", 12), submission(1, "2026-09-01", 16)] });
      const { container } = render(<TrendChart code="hhie-s" />);
      await chartDrawn(container);
      const drawn = [...container.querySelectorAll(".recharts-line-curve")].filter(
        (c) => c.getAttribute("stroke") !== "none" && vertices(c).length > 0,
      );
      expect(drawn).toHaveLength(1);
      expect(drawn[0].closest(".trend-line-unaided")).not.toBeNull();
    });

    it("puts each score inside its own level band (acceptance 10)", async () => {
      mockApi({
        results: [26, 24, 10, 8].map((total, i) => submission(4 - i, `2026-10-0${4 - i}`, total)),
      });
      const { container } = render(<TrendChart code="hhie-s" />);
      await chartDrawn(container);
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
