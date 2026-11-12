// Steps on a line: the home page's 照顧旅程 (#459) and my guide's 選配路線 (#467), the owner's
// pick I1 + I2 on the step interactions page.

// I2 (ADR 0028's 2026-11-12 exception): the ticks, the blue line and the ring play on the tab's
// first visit only (its own key, played, for each list), as the header wave does: the class
// plays on the page sets them going. Later visits and reduced motion show the end at once; until
// this runs the page shows the end too, so a visit that will not play never flickers. When in
// view is in-view.js's (data-play-in-view, ADR 0029).
export function playOnceATab(win, played, plays) {
  if (win.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (win.sessionStorage.getItem(played)) return;
  win.sessionStorage.setItem(played, "1");
  win.document.documentElement.classList.add(plays);
}

// I1: in each list, a step (a <details> matching item) opens to say what it is, one at a time;
// the current step's card stays open, not a <details>. Without JavaScript each step still opens,
// several at once.
export function openOneAtATime(doc, list, item) {
  for (const steps of doc.querySelectorAll(list)) {
    // toggle does not bubble: listen on the way down.
    steps.addEventListener(
      "toggle",
      (event) => {
        if (!event.target.open) return;
        for (const other of steps.querySelectorAll(`${item}[open]`)) {
          if (other !== event.target) other.open = false;
        }
      },
      true,
    );
  }
}
