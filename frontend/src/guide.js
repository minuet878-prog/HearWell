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
  const cards = [...row.children];
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const maximum = () => row.scrollWidth - row.clientWidth;
  // The last card may reach the end of the row before its left edge can align.
  const positions = () => cards.map((card) => Math.min(maximum(), card.offsetLeft));
  const goTo = (left) => row.scrollTo({ left, behavior: reducedMotion.matches ? "auto" : "smooth" });

  function updateButtons() {
    const offsets = positions();
    const active = offsets.reduce((best, left, index) =>
      Math.abs(left - row.scrollLeft) < Math.abs(offsets[best] - row.scrollLeft) ? index : best,
    0);
    const card = cards[active];
    const cardBox = card.getBoundingClientRect();
    const art = card.querySelector(".guide-card-art").getBoundingClientRect();
    const rowBox = row.getBoundingClientRect();
    arrows.style.setProperty("--guide-art-x", `${art.left + art.width / 2 - rowBox.left}px`);
    arrows.style.setProperty("--guide-art-y", `${card.offsetTop + art.top - cardBox.top + art.height / 2}px`);
    previous.disabled = row.scrollLeft <= 1;
    following.disabled = row.scrollLeft >= maximum() - 1;
  }

  previous.addEventListener("click", () => {
    goTo(positions().reverse().find((left) => left < row.scrollLeft - 1) ?? 0);
  });
  following.addEventListener("click", () => {
    goTo(positions().find((left) => left > row.scrollLeft + 1) ?? maximum());
  });
  row.addEventListener("scroll", updateButtons, { passive: true });
  window.addEventListener("resize", updateButtons);
  controls.setAttribute("data-guide-controls", "");
  updateButtons();
  arrows.hidden = false;
  if (window.ResizeObserver) {
    const layout = new ResizeObserver(updateButtons);
    layout.observe(row);
    for (const card of cards) layout.observe(card.querySelector(".guide-card-top"));
  }

  let start;
  row.addEventListener("pointerdown", (event) => {
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
    const current = row.scrollLeft;
    const nearest = positions().reduce((best, left) =>
      Math.abs(left - current) < Math.abs(best - current) ? left : best,
    );
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
