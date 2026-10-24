import { peekDraft } from "./draft.js";

// #326 E7 (#337): on the home and screening pages, one line per unfinished draft this account
// has in this browser. The page lists the questionnaires (continue_notice.html); the draft rules
// are the answer page's own (draft.js), read without deleting anything.
const ICON =
  '<svg class="continue-notice-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' +
  '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>';

export function showContinueNotice({ now = Date.now() } = {}) {
  const data = document.getElementById("continue-notice-data");
  const notice = document.getElementById("continue-notice");
  if (!data || !notice) return;
  const { userId, questionnaires } = JSON.parse(data.textContent);
  for (const questionnaire of questionnaires) {
    const draft = peekDraft({
      questionnaireId: questionnaire.id,
      userId,
      questionIds: questionnaire.questionIds,
      allowNotApplicable: questionnaire.allowNotApplicable,
      now,
    });
    if (!draft) continue;
    // The answer page's own words: 「還沒答完」 before item 1, else 「答到第 N 題」.
    const where = draft.step === 0 ? "還沒答完" : `答到第 ${draft.step} 題`;
    const line = document.createElement("p");
    line.className = "continue-notice";
    line.innerHTML = ICON;
    const text = document.createElement("span");
    text.textContent = `您上次的「${questionnaire.name}」${where}，答案都還在。`;
    const link = document.createElement("a");
    link.href = questionnaire.url;
    link.textContent = "接著答";
    text.append(link);
    line.append(text);
    notice.append(line);
  }
}
