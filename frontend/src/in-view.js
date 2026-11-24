// Spec #338 (ticket #341, ADR 0029): entrance animations wait until they are in view.

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

// A number counting up (spec #741, ADR 0077): from 0 to its own text in 0.9 seconds, quickly at
// first, then slowly. The text stays the end value all along, so a screen reader reads that; the
// number on screen is site.css's data-count-now, drawn over the text, which it hides meanwhile.
const COUNT_UP_MS = 900;

function countUp(element, win) {
  const end = Number(element.textContent);
  let start;
  const step = (time) => {
    start ??= time;
    const done = Math.min(1, (time - start) / COUNT_UP_MS);
    if (done === 1) {
      element.removeAttribute("data-count-now");
      element.setAttribute("data-count-done", "");
      return;
    }
    element.setAttribute("data-count-now", String(Math.round(end * (1 - (1 - done) ** 3))));
    win.requestAnimationFrame(step);
  };
  win.requestAnimationFrame(step);
}

// The play-once mechanism (spec #741, ADR 0077, on top of ADR 0029). Every entrance animation
// plays once, the first time it is in view; scrolling away and back does not play it again;
// reduced motion shows the end at once. A template opts in by marking:
// - data-play-in-view on the element, or on a box whose contents play together: site.css holds
//   its animations on their first frame until this adds data-in-view. The animation itself is
//   site.css's, for example the shared play-once-slide-up, play-once-stamp, play-once-ring and
//   play-once-gauge classes (see there for what each needs).
// - data-count-up on an element whose whole text is a number of days (a score is shown as it is,
//   ADR 0077 since 2026-11-21): it counts up from 0 once in view. It needs no data-play-in-view
//   of its own.
// Starts each of them the first time it is in view, and stops watching it. One inside something
// inert (a stacked card behind the front one, #754) is not seen yet: it waits until card-stack.js
// says, with a card-stack-show event, that its card came to the front. One put in later (the
// guest result page's result, fetched first: Codex cross review of #741) is watched from then on;
// one that played already stays played.
const MARKED = "[data-play-in-view]:not([data-in-view]), [data-count-up]:not([data-count-done]):not([data-in-view])";

export function setUpPlayInView(win = window) {
  const doc = win.document;
  const reducedMotion = win.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // The marked elements in these nodes, the nodes included. Reduced motion: every number is
  // simply its end value (site.css has no animation to hold).
  const marked = (nodes) => {
    const found = nodes.flatMap((node) => [node, ...node.querySelectorAll(MARKED)]);
    if (reducedMotion) {
      for (const element of found) {
        if (element.matches("[data-count-up]")) element.setAttribute("data-count-done", "");
      }
    }
    return found.filter((element) => element.matches(MARKED));
  };
  let waiting = marked([doc.documentElement]);
  let layout;
  const check = () => {
    const inset = tabBarInset(win);
    waiting = waiting.filter((element) => {
      if (element.closest("[inert]")) return true;
      if (!isInView(element.getBoundingClientRect(), win.innerHeight, inset)) return true;
      element.setAttribute("data-in-view", "");
      if (element.hasAttribute("data-count-up")) countUp(element, win);
      return false;
    });
    if (waiting.length === 0) {
      win.removeEventListener("scroll", check);
      win.removeEventListener("resize", check);
      doc.removeEventListener("card-stack-show", check);
      layout?.disconnect();
    }
  };
  // Adding a listener it has already does nothing, so this starts watching again or goes on.
  const watch = () => {
    win.addEventListener("scroll", check, { passive: true });
    win.addEventListener("resize", check);
    doc.addEventListener("card-stack-show", check);
    layout?.observe(doc.body);
  };
  // The page changing height without a scroll (a fold opening, a late font, a chart growing, the
  // text size) can bring an element into view too. iPhones before iOS 13.4 have no ResizeObserver.
  if (win.ResizeObserver) layout = new win.ResizeObserver(check);
  watch();
  check();
  // Taken over: layout.html's fallback, which would play them all at once, is called off.
  win.clearTimeout(win.playInViewFallback);

  new win.MutationObserver((records) => {
    const added = records.flatMap((record) => [...record.addedNodes]);
    const fresh = marked(added.filter((node) => node.nodeType === Node.ELEMENT_NODE));
    const more = fresh.filter((element) => !waiting.includes(element));
    if (more.length === 0) return;
    waiting.push(...more);
    watch();
    check();
  }).observe(doc.body, { childList: true, subtree: true });
}
