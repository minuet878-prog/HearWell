// #334 (spec #326 D3, ADR 0028): a slow page can paint before its switch is parsed, and the
// pill's transition would then only fade the old pill out. Then it changes page without the
// transition, as a browser without one does. A classic script in <head>, so it listens before
// the first paint; switch-slide.js, a module, runs only after the page is parsed.
(function () {
  const PILL = ".records-switch a[aria-current='page'], .ear-switch a[aria-current='true']";
  addEventListener("pagereveal", function (event) {
    if (event.viewTransition && !document.querySelector(PILL)) {
      event.viewTransition.skipTransition();
    }
  });
})();
