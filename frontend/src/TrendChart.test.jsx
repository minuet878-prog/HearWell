import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TrendChart from "./TrendChart.jsx";

const LEVELS = [
  { code: "normal", text: "無/極輕微影響", max: 8 },
  { code: "mild_to_moderate", text: "輕度到中度影響", max: 24 },
  { code: "severe", text: "顯著影響", max: 40 },
];

function submission(id, date, total, text = "輕度到中度影響", questionnaire = { code: "hhie-s", name: "HHIE-S" }) {
  return {
    id,
    created_at: `${date}T14:30:00+08:00`,
    questionnaire,
    wearing_hearing_aid: null,
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

function dotHeights(container) {
  return [...container.querySelectorAll(".recharts-line-dots circle")].map((c) => Number(c.getAttribute("cy")));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("TrendChart", () => {
  // jsdom has no ResizeObserver, so ResponsiveContainer keeps its initialDimension and draws the chart.
  it("shows the summary, the title and a labelled band per level", async () => {
    mockApi({ results: [submission(2, "2026-10-14", 18), submission(1, "2026-09-01", 12)] });
    const { container } = render(<TrendChart />);
    await screen.findByText(/最近一次/);
    expect(summaryLines(container)).toEqual([
      "最近一次（2026/10/14）",
      "18 分 輕度到中度影響",
      "比上一次增加 6 分。",
    ]);
    const bands = [...container.querySelectorAll(".recharts-reference-area-rect")];
    expect(bands.map((b) => [b.getAttribute("y1"), b.getAttribute("y2")])).toEqual([
      ["0", "8"],
      ["8", "24"],
      ["24", "40"],
    ]);
    expect(screen.getByRole("heading", { name: /HHIE-S/ })).toBeTruthy();
    for (const level of LEVELS) {
      expect(screen.getAllByText(level.text, { selector: "text, tspan" }).length).toBeGreaterThan(0);
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
    const { container } = render(<TrendChart />);
    await screen.findByText(/最近一次/);
    expect(summaryLines(container).slice(1)).toEqual(["0 分 無/極輕微影響", "比上一次減少 18 分。"]);
    const heights = dotHeights(container);
    expect(heights).toHaveLength(3);
    expect(heights[2]).toBe(plotBottom(container));
  });

  it("draws scores of 0 at the bottom even without levels", async () => {
    mockApi({ results: [submission(2, "2026-10-14", 0), submission(1, "2026-09-01", 0)], levels: [] });
    const { container } = render(<TrendChart />);
    await screen.findByText(/和上一次相同。/);
    const bottom = plotBottom(container);
    expect(dotHeights(container)).toEqual([bottom, bottom]);
  });

  it("follows the newest submission's questionnaire", async () => {
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
    const { container } = render(<TrendChart />);
    await screen.findByText(/最近一次/);
    expect(screen.getByRole("heading").textContent).toBe("HHIA-S 總分變化");
    expect(dotHeights(container)).toHaveLength(2);
    expect(container.querySelector(".recharts-reference-area")).toBeNull();
  });

  it("shows the hovered point's score even when several share a date", async () => {
    // Real data: more than one screening on the same day.
    mockApi({
      results: [
        submission(4, "2026-10-14", 12),
        submission(3, "2026-10-14", 28),
        submission(2, "2026-10-14", 40),
        submission(1, "2026-08-01", 0, "無/極輕微影響"),
      ],
    });
    const { container } = render(<TrendChart />);
    await screen.findByText(/最近一次/);
    const dots = [...container.querySelectorAll(".recharts-line-dots circle")];
    const expectTooltipAt = async (dot, text) => {
      // jsdom puts the chart at (0, 0), so a dot's cx/cy are also its client coordinates.
      fireEvent.mouseMove(container.querySelector(".recharts-wrapper"), {
        clientX: Number(dot.getAttribute("cx")),
        clientY: Number(dot.getAttribute("cy")),
      });
      // Recharts handles mouse moves on the next animation frame.
      await vi.waitFor(() =>
        expect(container.querySelector(".recharts-tooltip-wrapper").textContent).toContain(text),
      );
    };
    await expectTooltipAt(dots[1], "40 分");
    await expectTooltipAt(dots[2], "28 分");
    await expectTooltipAt(dots[3], "12 分");
    // Dates, not ids, are what the user sees on the axis and in the tooltip.
    expect(container.querySelector(".recharts-tooltip-wrapper").textContent).toContain("2026/10/14");
    const ticks = [...container.querySelectorAll(".recharts-xAxis-tick-labels .recharts-cartesian-axis-tick-value")];
    expect(ticks.map((t) => t.textContent)).toEqual(["2026/08/01", "2026/10/14", "2026/10/14", "2026/10/14"]);
  });

  it("draws no bands when the questionnaire has no levels", async () => {
    mockApi({ results: [submission(1, "2026-10-14", 18)], levels: [] });
    const { container } = render(<TrendChart />);
    await screen.findByText(/最近一次/);
    expect(container.querySelector(".recharts-line")).not.toBeNull();
    expect(container.querySelector(".recharts-reference-area")).toBeNull();
  });

  it("shows one point and how to see a change", async () => {
    mockApi({ results: [submission(1, "2026-10-14", 18)] });
    render(<TrendChart />);
    expect(await screen.findByText(/再做一次篩檢，就能看到分數的變化。/)).toBeTruthy();
  });

  it("renders nothing without submissions", async () => {
    mockApi({ results: [] });
    const { container } = render(<TrendChart />);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    await Promise.resolve();
    expect(container.textContent).toBe("");
  });

  it("only uses the first page (latest 20)", async () => {
    const results = Array.from({ length: 20 }, (_, i) => submission(20 - i, "2026-10-14", 10));
    mockApi({ results, next: "/api/submissions/?cursor=abc" });
    render(<TrendChart />);
    await screen.findByText(/最近一次/);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("shows the API's level text, not a recomputed one", async () => {
    mockApi({ results: [submission(1, "2026-10-14", 18, "假的分級")] });
    render(<TrendChart />);
    expect(await screen.findByText("假的分級")).toBeTruthy();
  });

  it("explains when the API returns an error", async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }));
    render(<TrendChart />);
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

    it("draws the line in the primary colour and highlights the latest point", async () => {
      threePoints();
      const { container } = render(<TrendChart />);
      await screen.findByText(/最近一次/);
      expect(container.querySelector(".recharts-line-curve").getAttribute("stroke")).toBe("#1f4e8c");
      const dots = [...container.querySelectorAll(".recharts-line-dots circle")];
      const [older, latest] = [dots.slice(0, -1), dots.at(-1)];
      expect(latest.getAttribute("fill")).toBe("#1f4e8c");
      for (const dot of older) {
        expect(dot.getAttribute("fill")).toBe("#fff");
        expect(dot.getAttribute("stroke")).toBe("#1f4e8c");
        expect(Number(dot.getAttribute("r"))).toBeLessThan(Number(latest.getAttribute("r")));
      }
    });

    it("writes each score next to its point, including 0", async () => {
      threePoints();
      const { container } = render(<TrendChart />);
      await screen.findByText(/最近一次/);
      const labels = [...container.querySelectorAll(".trend-score")].map((t) => t.textContent);
      expect(labels).toEqual(["12", "18", "0"]);
    });

    it("uses soft band colours, level-coloured labels and no y axis numbers", async () => {
      threePoints();
      const { container } = render(<TrendChart />);
      await screen.findByText(/最近一次/);
      const bands = [...container.querySelectorAll(".recharts-reference-area-rect")];
      expect(bands.map((b) => b.getAttribute("fill"))).toEqual(["#e3f4ec", "#fff4d6", "#feece7"]);
      const labelColours = LEVELS.map(
        (level) => screen.getByText(level.text, { selector: "text, tspan" }).closest("text").getAttribute("fill"),
      );
      expect(labelColours).toEqual(["#1e7b55", "#8a5a00", "#c23b1c"]);
      const ticks = [...container.querySelectorAll(".recharts-yAxis-tick-labels .recharts-cartesian-axis-tick-value")];
      expect(ticks).toEqual([]);
    });

    it("orders title, summary box and chart card, with the summary outside the card", async () => {
      threePoints();
      const { container } = render(<TrendChart />);
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
      const { container } = render(<TrendChart />);
      await screen.findByText(/最近一次/);
      const dates = [...container.querySelectorAll(".recharts-xAxis-tick-labels text")];
      expect(dates.length).toBeGreaterThan(0);
      for (const date of dates) {
        expect(Number(date.getAttribute("y")) - plotBottom(container)).toBeGreaterThanOrEqual(16);
      }
    });

    it("summary box: date, big score with level, then the change", async () => {
      mockApi({ results: [submission(2, "2026-10-14", 12), submission(1, "2026-09-01", 28)] });
      const { container } = render(<TrendChart />);
      await screen.findByText(/最近一次/);
      expect(summaryLines(container)).toEqual([
        "最近一次（2026/10/14）",
        "12 分 輕度到中度影響",
        "比上一次減少 16 分。",
      ]);
      expect(container.querySelector(".trend-summary-score strong").textContent).toBe("12 分");
    });

    it("summary box with one submission and a score of 0", async () => {
      mockApi({ results: [submission(1, "2026-10-14", 0, "無/極輕微影響")] });
      const { container } = render(<TrendChart />);
      await screen.findByText(/最近一次/);
      expect(summaryLines(container)).toEqual([
        "最近一次（2026/10/14）",
        "0 分 無/極輕微影響",
        "再做一次篩檢，就能看到分數的變化。",
      ]);
    });
  });

  it("explains when the network fails", async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    render(<TrendChart />);
    expect(await screen.findByText(ERROR_TEXT)).toBeTruthy();
  });
});
