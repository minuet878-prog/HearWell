// Pure data helpers for the trend chart. Scores and level text come from the API as is (rule 10).

export function selectPoints(submissions, code) {
  // submissions: one API page, newest first. Mixing questionnaires would mix level bands,
  // so only the questionnaire the page asks for is kept.
  return submissions
    .filter((s) => s.questionnaire.code === code)
    .map((s) => ({
      id: s.id,
      // created_at is already Taipei time ("2026-10-14T14:30:00+08:00").
      date: s.created_at.slice(0, 10).replaceAll("-", "/"),
      total: s.scores.total,
      levelText: s.level.text,
      // true / false / null (unrecorded), shown as the point's shape.
      wearing: s.wearing_hearing_aid,
    }))
    .reverse();
}

export function summarize(points) {
  // The pieces of the summary box; the wording of the change line is fixed by the spec.
  const latest = points.at(-1);
  let change = "再做一次篩檢，就能看到分數的變化。";
  if (points.length > 1) {
    const diff = latest.total - points.at(-2).total;
    if (diff > 0) change = `比上一次增加 ${diff} 分。`;
    else if (diff < 0) change = `比上一次減少 ${-diff} 分。`;
    else change = "和上一次相同。";
  }
  return { date: latest.date, total: latest.total, levelText: latest.levelText, change };
}
