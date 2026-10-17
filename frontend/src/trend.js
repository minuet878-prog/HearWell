// Pure data helpers for the trend chart. Scores and level text come from the API as is (rule 10).

const STATUS_TEXT = new Map([
  [false, "沒戴助聽器"],
  [true, "有戴助聽器"],
  [null, "助聽器未記錄"],
]);

export function selectPoints(submissions, code) {
  // submissions: one API page, newest first. Mixing questionnaires would mix level bands,
  // so only the questionnaire the page asks for is kept.
  return submissions
    .filter((s) => s.questionnaire.code === code)
    .map((s) => {
      const total = s.scores.total;
      const wearing = s.wearing_hearing_aid;
      return {
        id: s.id,
        // created_at is already Taipei time ("2026-10-14T14:30:00+08:00").
        date: s.created_at.slice(0, 10).replaceAll("-", "/"),
        time: s.created_at.slice(11, 16),
        total,
        levelText: s.level.text,
        // true / false / null (unrecorded), shown as the point's shape.
        wearing,
        // One series per status, so a line only joins records of the same status (spec 4.1).
        unaided: wearing === false ? total : null,
        aided: wearing === true ? total : null,
        unrecorded: wearing === null ? total : null,
      };
    })
    .reverse();
}

const SERIES = ["unaided", "aided", "unrecorded"];
const CHART_DAYS = 5;

export function chartDays(points) {
  // The chart's rows (spec 4.1): one per day, so a day's records share a column; the latest five
  // days; a later record of the same status replaces the earlier one (the cards list them all).
  const days = [];
  for (const p of points) {
    let day = days.at(-1);
    if (day?.date !== p.date) {
      day = { date: p.date, count: 0 };
      for (const key of SERIES) {
        Object.assign(day, { [key]: null, [`${key}Level`]: null, [`${key}Time`]: null });
      }
      days.push(day);
    }
    day.count += 1;
    for (const key of SERIES) {
      if (p[key] !== null) {
        Object.assign(day, { [key]: p[key], [`${key}Level`]: p.levelText, [`${key}Time`]: p.time });
      }
    }
  }
  return days.slice(-CHART_DAYS);
}

export function summarize(points) {
  // The pieces of the summary box; the wording is fixed by spec phase9_ui_refresh_2_data.md 4.2.
  const latest = points.at(-1);
  const statusText = STATUS_TEXT.get(latest.wearing);
  const previous = points.slice(0, -1).findLast((p) => p.wearing === latest.wearing);
  let change;
  if (points.length === 1) change = "再做一次篩檢，就能看到分數的變化。";
  else if (latest.wearing === null) change = "這筆沒有記錄助聽器，不和其他紀錄比較。";
  else if (!previous) change = `這是第一筆${statusText}的紀錄。`;
  else {
    const diff = latest.total - previous.total;
    const since = `上一次${statusText}（${previous.date}）`;
    if (diff > 0) change = `比${since}增加 ${diff} 分。`;
    else if (diff < 0) change = `比${since}減少 ${-diff} 分。`;
    else change = `和${since}相同。`;
  }
  return { date: latest.date, statusText, total: latest.total, levelText: latest.levelText, change };
}
