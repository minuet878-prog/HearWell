// The home page's 照顧旅程 (#459, the owner's pick I1 + I2 on the step interactions page).

// I2 (ADR 0028's 2026-11-12 exception): the ticks, the blue line and the ring play on the tab's
// first visit only, as the header wave does; later visits and reduced motion show the end at
// once. Until this runs the page shows the end too, so a visit that will not play never flickers.
// When in view is in-view.js's (data-play-in-view, ADR 0029).
export function playJourneyOnce(win = window) {
  if (win.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (win.sessionStorage.getItem("journey-played")) return;
  win.sessionStorage.setItem("journey-played", "1");
  win.document.documentElement.classList.add("journey-plays");
}

// I1: a step opens to say what it is, one at a time; the 現在這一步's card stays open, not a
// <details>. Without JavaScript each step still opens, several at once.
export function setUpJourneySteps(doc = document) {
  for (const list of doc.querySelectorAll(".journey-steps")) {
    // toggle does not bubble: listen on the way down.
    list.addEventListener(
      "toggle",
      (event) => {
        if (!event.target.open) return;
        for (const other of list.querySelectorAll(".journey-about[open]")) {
          if (other !== event.target) other.open = false;
        }
      },
      true,
    );
  }
}
