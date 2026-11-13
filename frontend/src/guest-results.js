// A guest's results kept in this browser (spec #492, ADR 0055): one per questionnaire, the newest,
// for 7 days. Beside the answer drafts (draft.js) under a key of their own, so neither touches
// the other. Every storage call may throw (private mode, blocked storage): then nothing is kept.
//
// A result: { code, questionnaireId, answers: [{ question, score }], wearing, key (the receipt
// number its saving will send), finishedAt, total, level: { code, text, color } }; total and
// level are the server's, for the home page.
export const GUEST_PREFIX = "hearwell:guest-result:";
export const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
const LOAD_FAILED = "結果載入失敗，請重新整理這一頁";

function attempt(action) {
  try {
    return action();
  } catch {
    return null;
  }
}

function parse(raw) {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function isUsable(result, code, now) {
  return (
    typeof result === "object" &&
    result !== null &&
    result.code === code &&
    Number.isFinite(result.finishedAt) &&
    now - result.finishedAt <= MAX_AGE_MS &&
    Array.isArray(result.answers)
  );
}

// True only when the browser kept it.
export function saveGuestResult(result) {
  return attempt(() => {
    localStorage.setItem(GUEST_PREFIX + result.code, JSON.stringify(result));
    return true;
  }) ?? false;
}

export function clearGuestResult(code) {
  attempt(() => localStorage.removeItem(GUEST_PREFIX + code));
}

// Also deletes every guest result that must not stay: expired or broken.
export function loadGuestResult(code, now = Date.now()) {
  const keys = attempt(() => Object.keys(localStorage).filter((key) => key.startsWith(GUEST_PREFIX))) ?? [];
  for (const key of keys) {
    const kept = parse(attempt(() => localStorage.getItem(key)));
    if (!isUsable(kept, key.slice(GUEST_PREFIX.length), now)) attempt(() => localStorage.removeItem(key));
  }
  const result = parse(attempt(() => localStorage.getItem(GUEST_PREFIX + code)));
  return isUsable(result, code, now) ? result : null;
}

// Every guest result kept, the ones that must not stay deleted first.
export function loadGuestResults(now = Date.now()) {
  const keys = attempt(() => Object.keys(localStorage).filter((key) => key.startsWith(GUEST_PREFIX))) ?? [];
  return keys.map((key) => loadGuestResult(key.slice(GUEST_PREFIX.length), now)).filter((result) => result !== null);
}

const DAY_MS = 24 * 60 * 60 * 1000;
// Whole days before it is deleted, a part of a day counted as one: 7 just finished, 5 two days after.
export const daysLeft = (finishedAt, now) => Math.ceil((finishedAt + MAX_AGE_MS - now) / DAY_MS);

const pad = (number) => String(number).padStart(2, "0");
export const day = (time) => {
  const date = new Date(time);
  return `${date.getFullYear()}/${pad(date.getMonth() + 1)}/${pad(date.getDate())}`;
};

// Nothing of the result left on the page, so the browser's cache of it shows none either.
function emptyPage(root) {
  root.querySelector("[data-guest-shown]").hidden = true;
  root.querySelector("[data-guest-section]").innerHTML = "";
}

// #498 (the #493 mockup's E1): 清除這次結果 opens its question under it, with focus there and its
// buttons in view; 不要 folds it back to the row, 清除 forgets only this questionnaire's result and
// goes home (navigate replaces this page in the history, so going back skips it).
function offerClearing(root, navigate) {
  const { code, homeUrl } = root.dataset;
  const row = root.querySelector("[data-guest-clear]");
  const no = row.querySelector("[data-guest-clear-no]");
  row.addEventListener("toggle", () => {
    if (!row.open) return;
    row.querySelector("[data-guest-clear-question]").focus();
    no.scrollIntoView({ block: "nearest" });
  });
  no.addEventListener("click", () => {
    row.open = false;
    row.querySelector("summary").focus();
  });
  row.querySelector("[data-guest-clear-yes]").addEventListener("click", () => {
    clearGuestResult(code);
    emptyPage(root);
    navigate(homeUrl);
  });
}

// The guest result page (guest_result.html): the kept answers scored again by the server, which
// draws the result page's section; without a result (none, expired, cleared) it goes home.
export async function showGuestResult({
  root,
  now = Date.now(),
  fetchScore = (...args) => fetch(...args),
  navigate = (url) => window.location.replace(url),
}) {
  const { code, scoreUrl, homeUrl } = root.dataset;
  const result = loadGuestResult(code, now);
  if (result === null) {
    // Back from the browser's cache after it went: nothing of it stays on screen.
    emptyPage(root);
    return navigate(homeUrl);
  }
  const error = root.querySelector("[data-guest-error]");
  let response = null;
  try {
    response = await fetchScore(scoreUrl, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": root.querySelector("[name=csrfmiddlewaretoken]")?.value,
      },
      body: JSON.stringify({
        questionnaire: result.questionnaireId,
        wearing_hearing_aid: result.wearing,
        answers: result.answers,
        just_finished: false,
      }),
    });
  } catch {
    // Network failure: the result stays for another try.
  }
  const body = response ? await response.json().catch(() => ({})) : {};
  if (response?.ok) {
    root.querySelector("[data-guest-date]").textContent = day(result.finishedAt);
    root.querySelector("[data-guest-wearing]").textContent = body.wearing_text;
    root.querySelector("[data-guest-section]").innerHTML = body.html;
    // The save card's days left (save_card.html): only this browser knows when it was finished.
    const days = root.querySelector("[data-guest-days-left]");
    if (days) days.textContent = String(daysLeft(result.finishedAt, now));
    offerClearing(root, navigate);
    root.querySelector("[data-guest-shown]").hidden = false;
    error.textContent = "";
  } else if (response?.status === 400) {
    // Kept answers the server cannot score (changed by hand, or a questionnaire gone).
    clearGuestResult(code);
    navigate(homeUrl);
  } else {
    error.textContent = response?.status === 429 && body.detail ? body.detail : LOAD_FAILED;
  }
}

// The save page (guest_save.html, spec #492): every guest result sent to the records API as the
// answer page sends an account's answers, with its own receipt number (a resend makes no second
// record) and the guest mark. One saved leaves this browser; one not saved stays and is named.
// All saved: 我的紀錄; none here: home.
export async function saveGuestResults({
  root,
  now = Date.now(),
  fetchSave = (...args) => fetch(...args),
  navigate = (url) => window.location.replace(url),
}) {
  const { submissionsUrl, doneUrl, homeUrl } = root.dataset;
  const results = loadGuestResults(now);
  if (results.length === 0) return navigate(homeUrl);
  const saving = root.querySelector("[data-guest-saving]");
  const failedBox = root.querySelector("[data-guest-failed]");
  saving.hidden = false;
  failedBox.hidden = true;
  const failed = [];
  for (const result of results) {
    let response = null;
    try {
      response = await fetchSave(submissionsUrl, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": root.querySelector("[name=csrfmiddlewaretoken]")?.value,
          "Idempotency-Key": result.key,
        },
        body: JSON.stringify({
          questionnaire: result.questionnaireId,
          wearing_hearing_aid: result.wearing,
          answers: result.answers,
          from_guest: true,
        }),
      });
    } catch {
      // Network failure: it stays, for 再試一次 with the same receipt number.
    }
    if (response?.ok) clearGuestResult(result.code);
    else failed.push(result);
  }
  if (failed.length === 0) return navigate(doneUrl);
  const names = JSON.parse(root.querySelector("#guest-names").textContent);
  root.querySelector("[data-guest-failed-list]").replaceChildren(
    ...failed.map((result) => {
      const line = document.createElement("p");
      line.textContent = `「${names[result.code] ?? result.code}」沒有存成，還留在這支手機上，請再試一次。`;
      return line;
    }),
  );
  saving.hidden = true;
  failedBox.hidden = false;
  root
    .querySelector("[data-guest-retry]")
    .addEventListener("click", () => saveGuestResults({ root, fetchSave, navigate }), { once: true });
}
