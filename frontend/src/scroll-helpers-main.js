// Spec #338: the site-wide scroll helpers, one module each; layout.html loads this on every page.
import { setUpBackToTop } from "./back-to-top.js";
import { setUpPlayInView } from "./in-view.js";
import { setUpJumpHighlight } from "./jump-highlight.js";
import { setUpScrollHint } from "./scroll-hint.js";

setUpBackToTop();
setUpPlayInView();
setUpJumpHighlight();
setUpScrollHint();
