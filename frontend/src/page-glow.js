// The owner's 2026-11-28 pick (G1, ADR 0087): every page's pale blue glow sits under its current
// tab, in the middle on a page with none (or where the tab bar is left out). layout.html puts it
// back where the page before left it before the first paint; this moves it to this page's tab,
// and site.css slides it there (not with reduced motion). Where it ends is kept for the next page.
export const GLOW_KEY = "hearwell:glow-x";

function glowX(doc) {
  const tab = doc.querySelector('.site-nav a[aria-current="page"]');
  const box = tab?.getBoundingClientRect();
  if (!box || box.width === 0) return "50%";
  const middle = (box.left + box.width / 2) / doc.documentElement.clientWidth;
  return `${Math.round(middle * 1000) / 10}%`;
}

export function setUpPageGlow(win = window) {
  const doc = win.document;
  const root = doc.documentElement;
  const glow = doc.querySelector(".page-glow > div");
  if (!glow) return;

  const place = () => {
    const x = glowX(doc);
    // Where the page before left it is drawn first, so the slide starts from there.
    win.getComputedStyle?.(glow).left;
    root.style.setProperty("--glow-x", x);
    try {
      win.sessionStorage.setItem(GLOW_KEY, x);
    } catch {
      // Nothing kept (a private window, blocked storage): the next page's glow just starts there.
    }
  };

  place();
  win.addEventListener("resize", place);
}
