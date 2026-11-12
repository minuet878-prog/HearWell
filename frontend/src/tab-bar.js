// #457 (ADR 0045): the bottom tab bar makes way while the page scrolls down and comes back on
// the way up. This only marks the bar (data-hidden); site.css slides it away on phones alone,
// so without JavaScript, and on wide screens, it always shows.
export function setUpTabBar(win = window) {
  // Reduced motion: the bar stays put, so none of this is set up (site.css never slides it
  // either, should the setting change after the page opened).
  if (win.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const doc = win.document;
  const bar = doc.querySelector(".site-nav");
  let lastY = win.scrollY;

  // Always there at the top of the page (an iPhone bounces past it and back down), at the bottom
  // (a pixel short where a zoomed page stops), and while the focus is on a tab.
  const mustShow = (y) =>
    y <= 0 ||
    y + win.innerHeight >= doc.documentElement.scrollHeight - 1 ||
    bar.contains(doc.activeElement);

  win.addEventListener("scroll", () => {
    const y = win.scrollY;
    if (mustShow(y)) bar.removeAttribute("data-hidden");
    else if (y !== lastY) bar.toggleAttribute("data-hidden", y > lastY);
    lastY = y;
  }, { passive: true });

  bar.addEventListener("focusin", () => bar.removeAttribute("data-hidden"));
}
