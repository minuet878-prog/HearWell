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

// Pixel y of the bottom of the plot (where a score of 0 belongs).
function plotBottom(container) {
  const axis = container.querySelector(".recharts-yAxis .recharts-cartesian-axis-line");
  return Math.max(Number(axis.getAttribute("y1")), Number(axis.getAttribute("y2")));
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
    expect(
      await screen.findByText("最近一次 2026/10/14：18 分，輕度到中度影響，比上一次增加 6 分。"),
    ).toBeTruthy();
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
    expect(await screen.findByText(/0 分，無\/極輕微影響，比上一次減少 18 分。/)).toBeTruthy();
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
    expect(await screen.findByText(/18 分，假的分級。/)).toBeTruthy();
  });

  it("explains when the API returns an error", async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }));
    render(<TrendChart />);
    expect(await screen.findByText(ERROR_TEXT)).toBeTruthy();
  });

  it("explains when the network fails", async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    render(<TrendChart />);
    expect(await screen.findByText(ERROR_TEXT)).toBeTruthy();
  });
});
