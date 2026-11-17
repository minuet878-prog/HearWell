// Pure data helpers for the trend chart. Scores and level text come from the API as is (rule 10).

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

// #650 (spec #644 R2): the two chart days the fitting day falls between, the same day twice
// when it is a record's day (the first and the last too); null without a day, or before the
// first or after the last day the chart shows, so no line is drawn outside the chart. Dates are
// YYYY/MM/DD, so they compare as text.
export function fittingDays(days, fittedOn) {
  if (!fittedOn || fittedOn < days[0].date || fittedOn > days.at(-1).date) return null;
  const after = days.findIndex((day) => day.date >= fittedOn);
  if (days[after].date === fittedOn) return [fittedOn, fittedOn];
  return [days[after - 1].date, days[after].date];
}
