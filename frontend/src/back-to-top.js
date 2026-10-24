// Spec #338 (ticket #340): a "↑ 回到頂端" button on long pages. Made here, so there is none
// without JavaScript; the CSS fades it in and out, and keeps it off paper.
import { tabBarInset } from "./in-view.js";

export const shouldShowBackToTop = (scrollY, viewportHeight) => scrollY > 2 * viewportHeight;

export function setUpBackToTop(win = window) {
  const doc = win.document;
  const main = doc.getElementById("main-content");
  const button = doc.createElement("button");
  button.type = "button";
  button.className = "btn btn-primary back-to-top";
  button.innerHTML = '<span aria-hidden="true">↑</span> 回到頂端';
  // After the content and before the footer, so the Tab order reaches it once the page is read.
  main.after(button);

  // Folded away, it is hidden from Tab and screen readers too (visibility: hidden in site.css).
  const update = () => {
    button.toggleAttribute("data-shown", shouldShowBackToTop(win.scrollY, win.innerHeight));
  };
  win.addEventListener("scroll", update, { passive: true });
  win.addEventListener("resize", update);
  update();

  // On phones it sits above the bottom tab bar, whose height grows with the text size; measured
  // as in-view.js measures it (0 on wide screens, where site.css does not use it).
  new win.ResizeObserver(() => {
    doc.documentElement.style.setProperty("--tab-bar-height", `${tabBarInset(win)}px`);
  }).observe(doc.querySelector(".site-nav"));

  // The scroll follows the site's smooth scrolling (instant with reduced motion); the focus moves
  // to the page's title without a jump of its own, so the next Tab goes on from there.
  button.addEventListener("click", () => {
    win.scrollTo({ top: 0 });
    const title = main.querySelector("h1") ?? main;
    if (!title.hasAttribute("tabindex")) title.tabIndex = -1;
    title.focus({ preventScroll: true });
  });
}
