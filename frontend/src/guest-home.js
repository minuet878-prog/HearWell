import { day, daysLeft, loadGuestResults } from "./guest-results.js";

// #499 (spec #492 acceptance 21, the #493 mockup's A1): on the logged-out home, which is the same
// for everyone and may be cached, each guest result kept in this browser is a tile in its level's
// colour (L1, as 上次結果 on a signed-in home), the whole tile a link to its guest result page.
// With two, one line on top says so instead of each tile.
const ONE = "您有一份還沒保存的結果";

function part(className, text) {
  const span = document.createElement("span");
  if (className) span.className = className;
  span.textContent = text;
  return span;
}

function tile(result, questionnaire, now, label) {
  const link = document.createElement("a");
  link.className = `journey-tile result-banner-${result.level.color} pr-10`;
  link.href = questionnaire.url;
  const score = part("journey-tile-score", `${result.total} `);
  score.append(Object.assign(document.createElement("small"), { textContent: "分" }));
  const arrow = part("journey-tile-arrow", "›");
  arrow.setAttribute("aria-hidden", "true");
  link.append(
    ...(label ? [part("journey-tile-label", label)] : []),
    part("", `${day(result.finishedAt)}・${questionnaire.topic}`),
    score,
    part("journey-tile-level", result.level.text),
    part("", `還留 ${daysLeft(result.finishedAt, now)} 天，看結果並保存`),
    arrow,
  );
  return link;
}

export function showGuestHome({ root, questionnaires, now = Date.now() }) {
  const results = loadGuestResults(now)
    .filter((result) => questionnaires[result.code])
    .sort((a, b) => b.finishedAt - a.finishedAt);
  const single = results.length === 1;
  const tiles = results.map((result) => tile(result, questionnaires[result.code], now, single ? ONE : null));
  if (results.length > 1) {
    const title = Object.assign(document.createElement("p"), {
      className: "m-0 font-bold",
      textContent: `您有 ${results.length} 份還沒保存的結果`,
    });
    tiles.unshift(title);
  }
  root.replaceChildren(...tiles);
  root.hidden = results.length === 0;
}
