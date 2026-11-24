// #334 (spec #326 D3, ADR 0028): site.css opts every page into the browser's cross-document view
// transition, in which only the blue pill of 問卷｜聽力圖 and 右耳｜左耳 takes part. Left alone,
// every change of page would run one, and leaving a page with a pill would fade that pill out.
// So the page being left skips the transition unless the last thing pressed was a switch.
// #748 (spec #741 P9): the tab bar's solid blue pill slides the same way.
const SWITCHES = ".records-switch, .ear-switch, .site-nav";

export function setUpSwitchSlide(win) {
  const doc = win.document;
  let switching = false;

  doc.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    switching = Boolean(link?.closest(SWITCHES) && !link.hasAttribute("aria-current"));
  });
  doc.addEventListener("submit", () => {
    switching = false;
  });
  // The back button can bring this page back from the cache with its switch pressed.
  win.addEventListener("pageshow", () => {
    switching = false;
  });

  win.addEventListener("pageswap", (event) => {
    if (!switching) event.viewTransition?.skipTransition();
  });
}
