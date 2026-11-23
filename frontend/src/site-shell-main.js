// Site-wide shell helpers loaded once by layout.html on every page (ADR 0080): combines PWA
// pull-to-refresh, page-loading indicator, view-transition switch slide, and scroll/header helpers
// into one module request while keeping each underlying module independently testable.
import { setUpBackToTop } from "./back-to-top.js";
import { setUpPlayInView } from "./in-view.js";
import { setUpJumpHighlight } from "./jump-highlight.js";
import { setUpPageLoading } from "./page-loading.js";
import { setUpPwaNav } from "./pwa-nav.js";
import { setUpScrollHint } from "./scroll-hint.js";
import { setUpAccountMenu, setUpSiteHeader } from "./site-header.js";
import { setUpSwitchSlide } from "./switch-slide.js";
import { setUpTabBar } from "./tab-bar.js";

// Each on its own: one that stops with an error leaves the others working. Play-in-view first,
// as the page's entrance animations hold their first frame until it takes over.
const helpers = [
  setUpPlayInView,
  setUpPwaNav,
  () => setUpPageLoading(window),
  () => setUpSwitchSlide(window),
  setUpBackToTop,
  setUpJumpHighlight,
  setUpScrollHint,
  setUpTabBar,
  setUpSiteHeader,
  setUpAccountMenu,
];
for (const setUp of helpers) {
  try {
    setUp();
  } catch (error) {
    console.error(error);
  }
}
