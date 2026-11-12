// #467: 我的選配指引's 選配路線 and the guide chapters' folds (H2). The route's steps share
// step-list.js with the home page's 照顧旅程 (#459).
import { playOnceATab } from "./step-list.js";

// I2: the route's entrance (step-list.js), but only with a 目前這一站 to play up to, and not while
// a stop just answered draws its own tick (#336): not both at once.
export function playRouteOnce(win = window) {
  const doc = win.document;
  if (!doc.querySelector(".route-stop.is-here")) return;
  if (doc.querySelector(".route-stop.is-done-now")) return;
  playOnceATab(win, "route-played", "route-plays");
}

// H2: a chapter's folds come open in the page, so without JavaScript every part shows in full.
// Here they fold away, all but the one a jump lands on (from the route, 補助檢核 or the
// assistant): the fold holding the target, or the one in the target's part. A later jump within
// the page opens its fold too. Until this has run, chapter.html hides the folds' contents, so the
// page does not show them all and then shrink.
export function openFoldsForJump(win = window) {
  const doc = win.document;
  const foldFor = (hash) => {
    const target = hash && doc.getElementById(decodeURIComponent(hash.slice(1)));
    if (!target) return null;
    return (
      target.closest("[data-guide-fold]") ??
      target.closest("section")?.querySelector("[data-guide-fold]") ??
      null
    );
  };
  const kept = foldFor(win.location.hash);
  for (const fold of doc.querySelectorAll("[data-guide-fold]")) {
    fold.open = fold === kept;
  }
  win.clearTimeout(win.guideFoldsFallback);
  doc.documentElement.classList.remove("guide-folds-pending");
  win.addEventListener("hashchange", () => {
    const fold = foldFor(win.location.hash);
    if (fold) fold.open = true;
  });
}
