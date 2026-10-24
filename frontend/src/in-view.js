// Spec #338 (ticket #341, ADR 0028): entrance animations wait until they are in view.

// In view: wholly inside what shows above the bottom tab bar (bottomInset), or, for an element
// taller than half of that, filling at least half of it. Only something that tall can fill half,
// so the second rule needs no height check of its own.
export function isInView(rect, viewportHeight, bottomInset) {
  const visible = viewportHeight - bottomInset;
  const shown = Math.min(rect.bottom, visible) - Math.max(rect.top, 0);
  return (rect.top >= 0 && rect.bottom <= visible) || shown >= visible / 2;
}

// The bottomInset for isInView: on phones the tab bar is fixed over the foot of the screen; on
// wide screens it is in the page.
export function tabBarInset(win) {
  const nav = win.document.querySelector(".site-nav");
  return win.getComputedStyle(nav).position === "fixed" ? nav.offsetHeight : 0;
}

// Starts each [data-play-in-view] animation (site.css holds it until then) the first time it is
// in view, and stops watching it: scrolling away and back does not play it again.
export function setUpPlayInView(win = window) {
  const doc = win.document;

  let waiting = [...doc.querySelectorAll("[data-play-in-view]")];
  const check = () => {
    const inset = tabBarInset(win);
    waiting = waiting.filter((element) => {
      if (!isInView(element.getBoundingClientRect(), win.innerHeight, inset)) return true;
      element.setAttribute("data-in-view", "");
      return false;
    });
    if (waiting.length === 0) {
      win.removeEventListener("scroll", check);
      win.removeEventListener("resize", check);
    }
  };
  win.addEventListener("scroll", check, { passive: true });
  win.addEventListener("resize", check);
  check();
  // Taken over: layout.html's fallback, which would play them all at once, is called off.
  win.clearTimeout(win.playInViewFallback);
}
