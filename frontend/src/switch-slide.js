// #334 (spec #326 D3, ADR 0028): site.css opts every page into the browser's cross-document view
// transition, in which only the blue pill of 問卷｜聽力圖 and 右耳｜左耳 takes part. Left alone,
// every change of page would run one, and leaving a page with a pill would fade that pill out.
// So the page being left skips the transition unless the last thing pressed was a switch.
const SWITCHES = ".records-switch, .ear-switch";

export function setUpSwitchSlide(win) {
  const doc = win.document;
  let switching = false;

  doc.addEventListener("click", (event) => {
    switching = Boolean(event.target.closest("a[href]")?.closest(SWITCHES));
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
