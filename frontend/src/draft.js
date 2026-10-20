// Unfinished answers kept in this browser (spec 4.2), one entry per questionnaire.
// Every storage call may throw (private mode, blocked storage): then nothing is kept.
export const DRAFT_PREFIX = "hearwell:answer-draft:";
export const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

function attempt(action) {
  try {
    return action();
  } catch {
    return null;
  }
}

function draftKeys() {
  return attempt(() => Object.keys(localStorage).filter((k) => k.startsWith(DRAFT_PREFIX))) ?? [];
}

function parse(raw) {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

// Owner and age are checked in loadDraft; this checks the content fits the questionnaire.
function isUsable(draft, questionIds, allowNotApplicable) {
  const isObject = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
  if (!isObject(draft) || !isObject(draft.answers)) return false;
  return (
    typeof draft.key === "string" &&
    [true, false, null].includes(draft.wearing) &&
    Number.isInteger(draft.step) &&
    draft.step >= 0 &&
    draft.step <= questionIds.length &&
    Object.entries(draft.answers).every(
      ([id, score]) => questionIds.includes(Number(id)) && (
        allowNotApplicable
          ? score === null || (Number.isInteger(score) && score >= 0 && score <= 10)
          : Number.isInteger(score)
      ),
    )
  );
}

export function saveDraft(draft) {
  attempt(() => localStorage.setItem(DRAFT_PREFIX + draft.questionnaireId, JSON.stringify(draft)));
}

export function clearDraft(questionnaireId) {
  attempt(() => localStorage.removeItem(DRAFT_PREFIX + questionnaireId));
}

export function clearAllDrafts() {
  draftKeys().forEach((key) => attempt(() => localStorage.removeItem(key)));
}

// Also deletes drafts that must not stay: another account's, expired or broken ones.
export function loadDraft({ questionnaireId, userId, questionIds, allowNotApplicable = false, now = Date.now() }) {
  for (const key of draftKeys()) {
    const draft = parse(attempt(() => localStorage.getItem(key)));
    const expired = !(now - draft?.savedAt <= MAX_AGE_MS);
    if (draft?.userId !== userId || expired) attempt(() => localStorage.removeItem(key));
  }
  const draft = parse(attempt(() => localStorage.getItem(DRAFT_PREFIX + questionnaireId)));
  if (draft === null) return null;
  if (isUsable(draft, questionIds, allowNotApplicable)) return draft;
  clearDraft(questionnaireId);
  return null;
}
