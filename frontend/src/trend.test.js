import { describe, expect, it } from "vitest";

import { selectPoints, summarize } from "./trend.js";

function submission(id, date, total, { code = "hhie-s", name = "HHIE-S", text = "無/極輕微影響" } = {}) {
  return {
    id,
    created_at: `${date}T14:30:00.123456+08:00`,
    questionnaire: { code, name },
    scores: { total, emotional: 0, social: 0 },
    level: { code: "normal", text },
  };
}

describe("selectPoints", () => {
  it("orders oldest to newest and keeps a score of 0", () => {
    // The API returns newest first.
    const points = selectPoints([
      submission(3, "2026-10-14", 0),
      submission(2, "2026-09-01", 18),
      submission(1, "2026-08-01", 12),
    ]);
    expect(points.map((p) => p.total)).toEqual([12, 18, 0]);
    expect(points.map((p) => p.date)).toEqual(["2026/08/01", "2026/09/01", "2026/10/14"]);
  });

  it("keeps only the questionnaire of the newest submission", () => {
    const points = selectPoints([
      submission(3, "2026-10-14", 10, { code: "hhia-s", name: "HHIA-S" }),
      submission(2, "2026-09-01", 20),
      submission(1, "2026-08-01", 30, { code: "hhia-s", name: "HHIA-S" }),
    ]);
    expect(points.map((p) => p.id)).toEqual([1, 3]);
  });

  it("uses the level text from the API as is", () => {
    const [point] = selectPoints([submission(1, "2026-10-14", 5, { text: "假的分級" })]);
    expect(point.levelText).toBe("假的分級");
  });

  it("returns no points for no submissions", () => {
    expect(selectPoints([])).toEqual([]);
  });
});

describe("summarize", () => {
  const point = (total, date = "2026/10/14", levelText = "輕度到中度影響") => ({ total, date, levelText });
  const latest = { date: "2026/10/14", total: 18, levelText: "輕度到中度影響" };

  it("explains how to see a change when there is one point", () => {
    expect(summarize([point(18)])).toEqual({ ...latest, change: "再做一次篩檢，就能看到分數的變化。" });
  });

  it("reports an increase", () => {
    expect(summarize([point(12), point(18)])).toEqual({ ...latest, change: "比上一次增加 6 分。" });
  });

  it("reports a decrease down to 0", () => {
    expect(summarize([point(12), point(18), point(0, "2026/10/14", "無/極輕微影響")])).toEqual({
      date: "2026/10/14",
      total: 0,
      levelText: "無/極輕微影響",
      change: "比上一次減少 18 分。",
    });
  });

  it("reports no change", () => {
    expect(summarize([point(18), point(18)])).toEqual({ ...latest, change: "和上一次相同。" });
  });
});
