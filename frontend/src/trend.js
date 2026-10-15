// Pure data helpers for the trend chart. Scores and level text come from the API as is (rule 10).

export function selectPoints(submissions) {
  // submissions: one API page, newest first. Mixing questionnaires would mix level bands,
  // so only the newest submission's questionnaire is kept.
  if (submissions.length === 0) return [];
  const { code } = submissions[0].questionnaire;
  return submissions
    .filter((s) => s.questionnaire.code === code)
    .map((s) => ({
      id: s.id,
      // created_at is already Taipei time ("2026-10-14T14:30:00+08:00").
      date: s.created_at.slice(0, 10).replaceAll("-", "/"),
      total: s.scores.total,
      levelText: s.level.text,
    }))
    .reverse();
}

export function summarize(points) {
  const latest = points.at(-1);
  const head = `最近一次 ${latest.date}：${latest.total} 分，${latest.levelText}`;
  if (points.length === 1) return `${head}。再做一次篩檢，就能看到分數的變化。`;
  const diff = latest.total - points.at(-2).total;
  if (diff > 0) return `${head}，比上一次增加 ${diff} 分。`;
  if (diff < 0) return `${head}，比上一次減少 ${-diff} 分。`;
  return `${head}，和上一次相同。`;
}
