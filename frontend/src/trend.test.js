import { describe, expect, it } from "vitest";

import { chartDays, selectPoints, summarize } from "./trend.js";

function submission(
  id,
  date,
  total,
  { code = "hhie-s", name = "HHIE-S", text = "無/極輕微影響", wearing = null } = {},
) {
  return {
    id,
    // "2026-10-15" gets 14:30; "2026-10-15T16:10" keeps its own time.
    created_at: `${date.includes("T") ? date : `${date}T14:30`}:00.123456+08:00`,
    questionnaire: { code, name },
    wearing_hearing_aid: wearing,
    scores: { total, emotional: 0, social: 0 },
    level: { code: "normal", text },
  };
}

describe("selectPoints", () => {
  it("orders oldest to newest and keeps a score of 0", () => {
    // The API returns newest first.
    const points = selectPoints(
      [submission(3, "2026-10-14", 0), submission(2, "2026-09-01", 18), submission(1, "2026-08-01", 12)],
      "hhie-s",
    );
    expect(points.map((p) => p.total)).toEqual([12, 18, 0]);
    expect(points.map((p) => p.date)).toEqual(["2026/08/01", "2026/09/01", "2026/10/14"]);
  });

  it("keeps only the questionnaire it is given, even if another is newer", () => {
    const submissions = [
      submission(3, "2026-10-14", 10, { code: "hhia-s", name: "HHIA-S" }),
      submission(2, "2026-09-01", 20),
      submission(1, "2026-08-01", 30, { code: "hhia-s", name: "HHIA-S" }),
    ];
    expect(selectPoints(submissions, "hhie-s").map((p) => p.id)).toEqual([2]);
    expect(selectPoints(submissions, "hhia-s").map((p) => p.id)).toEqual([1, 3]);
  });

  it("keeps the hearing aid status from the API, including unrecorded", () => {
    const points = selectPoints(
      [
        submission(3, "2026-10-14", 10, { wearing: null }),
        submission(2, "2026-09-01", 20, { wearing: true }),
        submission(1, "2026-08-01", 30, { wearing: false }),
      ],
      "hhie-s",
    );
    expect(points.map((p) => p.wearing)).toEqual([false, true, null]);
  });

  it("splits each score into the series of its hearing aid status (spec 4.1)", () => {
    const points = selectPoints(
      [
        submission(3, "2026-10-14", 10, { wearing: null }),
        submission(2, "2026-09-01", 0, { wearing: true }),
        submission(1, "2026-08-01", 30, { wearing: false }),
      ],
      "hhie-s",
    );
    expect(points.map(({ unaided, aided, unrecorded }) => [unaided, aided, unrecorded])).toEqual([
      [30, null, null],
      [null, 0, null],
      [null, null, 10],
    ]);
  });

  it("keeps the Taipei time of each record (spec 4.3)", () => {
    const points = selectPoints(
      [
        submission(3, "2026-10-15T16:10", 10),
        submission(2, "2026-10-15T09:05", 20),
        submission(1, "2026-10-01", 30),
      ],
      "hhie-s",
    );
    expect(points.map((p) => [p.date, p.time])).toEqual([
      ["2026/10/01", "14:30"],
      ["2026/10/15", "09:05"],
      ["2026/10/15", "16:10"],
    ]);
  });

  it("uses the level text from the API as is", () => {
    const [point] = selectPoints([submission(1, "2026-10-14", 5, { text: "假的分級" })], "hhie-s");
    expect(point.levelText).toBe("假的分級");
  });

  it("returns no points for no submissions", () => {
    expect(selectPoints([], "hhie-s")).toEqual([]);
  });
});

describe("chartDays", () => {
  // Spec 4.1: one column per day, the latest five days, the day's last record of each status.
  const point = (date, time, wearing, total, levelText = "輕度到中度影響") => ({
    date,
    time,
    wearing,
    total,
    levelText,
    unaided: wearing === false ? total : null,
    aided: wearing === true ? total : null,
    unrecorded: wearing === null ? total : null,
  });

  it("puts a day's records in one column (acceptance 16)", () => {
    const days = chartDays([point("2026/10/15", "14:30", false, 20), point("2026/10/15", "16:10", true, 10)]);
    expect(days).toHaveLength(1);
    expect(days[0]).toMatchObject({ date: "2026/10/15", count: 2, unaided: 20, aided: 10, unrecorded: null });
    expect(days[0]).toMatchObject({ unaidedTime: "14:30", aidedTime: "16:10", aidedLevel: "輕度到中度影響" });
  });

  it("keeps only the latest five days, oldest first (acceptance 17)", () => {
    const points = [1, 2, 3, 4, 5, 6, 7].map((day) => point(`2026/10/0${day}`, "09:00", false, day * 2));
    expect(chartDays(points).map((d) => d.date)).toEqual([
      "2026/10/03",
      "2026/10/04",
      "2026/10/05",
      "2026/10/06",
      "2026/10/07",
    ]);
  });

  it("draws only the day's last record of a status (acceptance 18)", () => {
    const [day] = chartDays([point("2026/10/15", "09:00", false, 10), point("2026/10/15", "15:00", false, 20)]);
    expect(day).toMatchObject({ count: 2, unaided: 20, unaidedTime: "15:00" });
  });

  it("keeps a score of 0 (not mistaken for no record)", () => {
    const [day] = chartDays([point("2026/10/15", "09:00", true, 0)]);
    expect(day.aided).toBe(0);
    expect(day.unaided).toBeNull();
  });
});

describe("summarize", () => {
  // Spec 4.2: compare only with the previous record of the same hearing aid status.
  const point = (total, wearing, date, levelText = "輕度到中度影響") => ({ total, wearing, date, levelText });

  it("names the latest status and keeps the API's score and level", () => {
    const summary = summarize([point(0, true, "2026/10/14", "無/極輕微影響")]);
    expect(summary).toMatchObject({ date: "2026/10/14", statusText: "有戴助聽器", total: 0, levelText: "無/極輕微影響" });
    expect(summarize([point(5, false, "2026/10/14")]).statusText).toBe("沒戴助聽器");
    expect(summarize([point(5, null, "2026/10/14")]).statusText).toBe("助聽器未記錄");
  });

  it("explains how to see a change when there is only one record", () => {
    expect(summarize([point(18, false, "2026/10/14")]).change).toBe("再做一次篩檢，就能看到分數的變化。");
  });

  it("finds the previous record of the status even before the chart's five days (acceptance 17)", () => {
    const points = [point(14, true, "2026/09/01")];
    for (const day of [2, 3, 4, 5, 6, 7]) points.push(point(20, false, `2026/10/0${day}`));
    points.push(point(10, true, "2026/10/08"));
    expect(summarize(points).change).toBe("比上一次有戴助聽器（2026/09/01）減少 4 分。");
  });

  it("skips records of the other status (acceptance 5)", () => {
    const points = [point(14, true, "2026/10/01"), point(20, false, "2026/10/15"), point(10, true, "2026/10/16")];
    expect(summarize(points).change).toBe("比上一次有戴助聽器（2026/10/01）減少 4 分。");
  });

  it("reports an increase, down to 0, and no change", () => {
    expect(summarize([point(12, false, "2026/09/01"), point(18, false, "2026/10/14")]).change).toBe(
      "比上一次沒戴助聽器（2026/09/01）增加 6 分。",
    );
    expect(summarize([point(18, false, "2026/09/01"), point(0, false, "2026/10/14")]).change).toBe(
      "比上一次沒戴助聽器（2026/09/01）減少 18 分。",
    );
    expect(summarize([point(18, true, "2026/09/01"), point(18, true, "2026/10/14")]).change).toBe(
      "和上一次有戴助聽器（2026/09/01）相同。",
    );
  });

  it("says it is the first of its status when only the other status came before (acceptance 6)", () => {
    expect(summarize([point(20, false, "2026/09/01"), point(10, true, "2026/10/14")]).change).toBe(
      "這是第一筆有戴助聽器的紀錄。",
    );
    expect(summarize([point(10, true, "2026/09/01"), point(20, false, "2026/10/14")]).change).toBe(
      "這是第一筆沒戴助聽器的紀錄。",
    );
  });

  it("does not compare an unrecorded record (acceptance 7)", () => {
    expect(summarize([point(10, null, "2026/09/01"), point(20, null, "2026/10/14")]).change).toBe(
      "這筆沒有記錄助聽器，不和其他紀錄比較。",
    );
  });
});
