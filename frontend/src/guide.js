// #467: the guide chapters' folds (H2). #779: my guide no longer draws the 選配路線, so its
// entrance went with it.

// H2: a chapter's folds come open in the page, so without JavaScript every part shows in full.
// Here they fold away, all but the one a jump lands on (from the route, 補助檢核 or the
// assistant): the fold holding the target, or the one in the target's part. A later jump within
// the page opens its fold too. Until this has run, chapter.html hides the folds' contents, so the
// page does not show them all and then shrink.
export function openFoldsForJump(win = window) {
  const doc = win.document;
  const foldFor = (hash) => {
    const target = hash && doc.getElementById(decodeURIComponent(hash.slice(1)));
    if (!target) return null;
    return (
      target.closest("[data-guide-fold]") ??
      target.closest("section")?.querySelector("[data-guide-fold]") ??
      null
    );
  };
  const kept = foldFor(win.location.hash);
  for (const fold of doc.querySelectorAll("[data-guide-fold]")) {
    fold.open = fold === kept;
  }
  win.clearTimeout(win.guideFoldsFallback);
  doc.documentElement.classList.remove("guide-folds-pending");
  win.addEventListener("hashchange", () => {
    const fold = foldFor(win.location.hash);
    if (fold) fold.open = true;
  });
}

export function setUpGuideCards(row) {
  const controls = row.parentElement;
  const arrows = controls.querySelector(".guide-card-arrows");
  const previous = controls.querySelector(".guide-card-prev");
  const following = controls.querySelector(".guide-card-next");
  const originals = [...row.children];

  function preview(card, buffer = false) {
    const copy = card.cloneNode(true);
    copy.classList.replace("guide-card", "guide-card-preview");
    copy.setAttribute("aria-hidden", "true");
    copy.setAttribute("inert", "");
    if (buffer) copy.setAttribute("data-guide-buffer", "");
    for (const node of copy.querySelectorAll("[id], [data-play-in-view], a")) {
      node.removeAttribute("id");
      node.removeAttribute("data-play-in-view");
      node.removeAttribute("href");
    }
    return copy;
  }

  // A copy at each end handles the wrap. An extra copy beyond it keeps both sides visible.
  const before = preview(originals[originals.length - 1]);
  const after = preview(originals[0]);
  row.prepend(preview(originals[originals.length - 2], true), before);
  row.append(after, preview(originals[1], true));
  const cards = [before, ...originals, after];
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const positions = () => cards.map((card) =>
    card.offsetLeft - (row.clientWidth - card.offsetWidth) / 2);
  const nearestIndex = (offsets) => {
    const current = row.scrollLeft;
    return offsets.reduce((best, left, index) =>
      Math.abs(left - current) < Math.abs(offsets[best] - current) ? index : best,
    0);
  };

  const queuedDirections = [];
  let moving = false;
  let scrollTimer;

  function checkWhenSettled() {
    arrows.setAttribute("data-guide-scrolling", "");
    window.clearTimeout(scrollTimer);
    scrollTimer = window.setTimeout(settle, 120);
  }

  function goTo(left) {
    moving = true;
    row.scrollTo({ left, behavior: reducedMotion.matches ? "auto" : "smooth" });
    checkWhenSettled();
  }

  function settle() {
    if (row.hasAttribute("data-dragging")) return;
    const offsets = positions();
    let index = nearestIndex(offsets);
    // Continue on the corresponding real card after its look-alike comes to rest.
    if (index === 0 || index === cards.length - 1) {
      index = index === 0 ? originals.length : 1;
      row.scrollTo({ left: offsets[index], behavior: "auto" });
    }
    moving = false;
    if (queuedDirections.length) {
      goTo(offsets[index + queuedDirections.shift()]);
    } else {
      arrows.removeAttribute("data-guide-scrolling");
    }
  }

  function requestStep(direction) {
    queuedDirections.push(direction);
    if (!moving) settle();
  }

  previous.addEventListener("click", () => requestStep(-1));
  following.addEventListener("click", () => requestStep(1));
  row.addEventListener("scroll", checkWhenSettled, { passive: true });
  controls.setAttribute("data-guide-controls", "");
  row.scrollTo({ left: positions()[1], behavior: "auto" });
  function placeArrows() {
    arrows.style.setProperty("--guide-card-center-y", `${originals[0].offsetHeight / 2}px`);
  }
  placeArrows();
  arrows.hidden = false;
  window.addEventListener("resize", placeArrows);
  if (window.ResizeObserver) {
    const layout = new ResizeObserver(placeArrows);
    layout.observe(row);
  }

  let start;
  row.addEventListener("pointerdown", (event) => {
    queuedDirections.length = 0;
    if (event.pointerType !== "mouse" || event.button !== 0) return;
    start = { x: event.clientX, left: row.scrollLeft, pointerId: event.pointerId };
  });
  row.addEventListener("dragstart", (event) => {
    if (start) event.preventDefault();
  });
  row.addEventListener("pointermove", (event) => {
    if (event.pointerId !== start?.pointerId || (event.buttons & 1) === 0) return;
    const delta = start.x - event.clientX;
    if (!row.hasAttribute("data-dragging")) {
      if (Math.abs(delta) <= 5) return;
      row.setPointerCapture(event.pointerId);
      row.setAttribute("data-dragging", "");
    }
    row.scrollLeft = start.left + delta;
  });
  function finish(event) {
    if (event.pointerId !== start?.pointerId) return;
    start = undefined;
    if (!row.hasAttribute("data-dragging")) return;
    const offsets = positions();
    const nearest = offsets[nearestIndex(offsets)];
    row.removeAttribute("data-dragging");
    goTo(nearest);
  }
  row.addEventListener("pointerup", finish);
  row.addEventListener("pointercancel", finish);
  row.addEventListener("lostpointercapture", finish);
  row.addEventListener("pointerleave", (event) => {
    if (!row.hasPointerCapture(event.pointerId)) finish(event);
  });
}
