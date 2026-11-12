// Spec #338 (and the tab bar of #457): the site-wide scroll helpers, one module each; layout.html
// loads this on every page.
import { setUpBackToTop } from "./back-to-top.js";
import { setUpPlayInView } from "./in-view.js";
import { setUpJumpHighlight } from "./jump-highlight.js";
import { setUpScrollHint } from "./scroll-hint.js";
import { setUpTabBar } from "./tab-bar.js";

// Each on its own: one that stops with an error leaves the others working. Play-in-view first,
// as the page's entrance animations hold their first frame until it takes over.
const helpers = [
  setUpPlayInView, setUpBackToTop, setUpJumpHighlight, setUpScrollHint, setUpTabBar,
];
for (const setUp of helpers) {
  try {
    setUp();
  } catch (error) {
    console.error(error);
  }
}
