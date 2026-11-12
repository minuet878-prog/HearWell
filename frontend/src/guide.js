// #467: 我的選配指引's 選配路線 (the owner's pick I1 + I2 on the step interactions page) and the
// guide chapters' folds (H2). The home page's 照顧旅程 (#459) does the same for its steps in its
// own module; the two are to become one.

// I2 (ADR 0028's 2026-11-12 exception): the done ticks, the blue line and the 目前這一站's ring
// play on the tab's first visit only, as the header wave does; later visits and reduced motion
// show the end at once. Until this runs the page shows the end too, so a visit that will not play
// never flickers. A stop just answered draws its own tick (#336): not both at once. When in view
// is in-view.js's (data-play-in-view, ADR 0029).
export function playRouteOnce(win = window) {
  const doc = win.document;
  if (!doc.querySelector(".route-stop.is-here")) return;
  if (doc.querySelector(".route-stop.is-done-now")) return;
  if (win.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (win.sessionStorage.getItem("route-played")) return;
  win.sessionStorage.setItem("route-played", "1");
  doc.documentElement.classList.add("route-plays");
}

// I1: a stop opens to say what it is, one at a time; the 您在這裡 card stays open, not a
// <details>. Without JavaScript each stop still opens, several at once.
export function setUpRouteStops(doc = document) {
  for (const list of doc.querySelectorAll(".route")) {
    // toggle does not bubble: listen on the way down.
    list.addEventListener(
      "toggle",
      (event) => {
        if (!event.target.open) return;
        for (const other of list.querySelectorAll(".route-about[open]")) {
          if (other !== event.target) other.open = false;
        }
      },
      true,
    );
  }
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
