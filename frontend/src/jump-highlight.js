// Spec #338 (ticket #343, ADR 0028): the box a jump lands on lights up for a moment.
import { isInView, tabBarInset } from "./in-view.js";

// The box to light: the nearest 段落框, 並列區塊 or route stop the target is in (a stop before
// the route's 段落框 around it), else the target itself. A 並列區塊 is beige (.tint-block), or
// marked data-parallel-block where its heading sits above the beige (the family page's topics).
export function jumpBox(target) {
  return target.closest(".section-box, .tint-block, [data-parallel-block], .route-stop") ?? target;
}

// Their links already mark the question in red (the answer page's, the 配戴比較 form's).
const ERROR_SUMMARIES = "#error-summary, #comparison-errors";
// Still: no scroll for this long. Also the wait when nothing scrolls at all (already there).
const PAUSE = 150;
// Held about 1.5 seconds and faded for 1.5 (site.css), then taken off.
const LIT_FOR = 3000;

export function setUpJumpHighlight(win = window) {
  const doc = win.document;

  // Where the browser says when a scroll ends (scrollend), a scroll only calls off the first
  // wait; elsewhere each scroll starts the wait again.
  const endsScrolls = "onscrollend" in win;

  // One box at a time: a new jump stops the last one, waiting or lit, at once.
  let stop = () => {};
  const light = (box) => {
    stop();
    let timer;
    const pause = () => {
      clearTimeout(timer);
      timer = setTimeout(settle, PAUSE);
    };
    const scrolled = endsScrolls ? () => clearTimeout(timer) : pause;
    const watch = (method) => {
      win[method]("scroll", scrolled, { passive: true });
      win[method]("scrollend", settle);
    };
    // Not yet in view, it waits for the next scroll to stop.
    function settle() {
      if (!isInView(box.getBoundingClientRect(), win.innerHeight, tabBarInset(win))) return;
      watch("removeEventListener");
      box.classList.add("jump-highlight");
      timer = setTimeout(() => box.classList.remove("jump-highlight"), LIT_FOR);
    }
    stop = () => {
      watch("removeEventListener");
      clearTimeout(timer);
      box.classList.remove("jump-highlight");
    };
    watch("addEventListener");
    pause();
  };

  // The skip link's landing, used on every page, lights nothing.
  const jumpTo = (hash) => {
    const target = doc.getElementById(decodeURIComponent(hash.slice(1)));
    if (target && target.id !== "main-content") light(jumpBox(target));
  };

  if (win.location.hash) jumpTo(win.location.hash);

  // A click, not the address changing: clicking the same link again changes nothing but lights
  // the box again.
  doc.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    // Only a jump within this page: a link anywhere else loads a page that lights its own box.
    const page = (address) => address.split("#")[0];
    if (!link?.hash || page(link.href) !== page(win.location.href)) return;
    if (!link.closest(ERROR_SUMMARIES)) jumpTo(link.hash);
  });
}
