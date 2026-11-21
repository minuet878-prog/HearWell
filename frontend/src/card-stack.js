// #753 (spec #741 P3, P4, acceptance 46, 56): stacked cards, one in front and the next ones
// peeking behind it. Drag the front card sideways past DRAG_THRESHOLD to change card, or less
// and it snaps back; ‹ › and the arrow keys change it too. Any page can use it (the
// questionnaires page, the learn page) with this markup:
//   .card-stack > .card-stack-cards > .card-stack-card × N, each with its own name and place
//   (aria-label), and card_stack_controls.html after the cards.
// Without JavaScript only the first card shows (site.css), the page's list below it. Changing
// card is the user's own doing, so it slides (not ADR 0077's play-once); under reduced motion
// the card changes without sliding or following the finger.
// A card's own play-once drawing (the learn page's, #754) plays when the card is at the front:
// write the cards after the first inert, so in-view.js holds their drawings, and each card coming
// to the front says so with a card-stack-show event.
export const DRAG_THRESHOLD = 50; // px
const MOVED = 4; // px: past this a press is a drag, not a tap on the card's link
const PEEK = 2; // cards shown behind the front one on each side

export function setUpCardStack(root, win = window) {
  const cards = [...root.querySelectorAll(".card-stack-card")];
  if (cards.length < 2) return;
  const track = root.querySelector(".card-stack-cards");
  const prev = root.querySelector(".card-stack-prev");
  const next = root.querySelector(".card-stack-next");
  const position = root.querySelector(".card-stack-position");
  const dots = [...root.querySelectorAll(".card-stack-dots > span")];
  const reduced = win.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const last = cards.length - 1;
  let index = 0;

  function show(to) {
    index = Math.max(0, Math.min(last, to));
    cards.forEach((card, n) => {
      const offset = n - index;
      card.dataset.offset = String(Math.max(-PEEK, Math.min(PEEK, offset)));
      // Only the front card is read and reached; the others are what peeks behind it.
      if (offset === 0) card.removeAttribute("aria-hidden");
      else card.setAttribute("aria-hidden", "true");
      card.inert = offset !== 0;
    });
    dots.forEach((dot, n) => dot.toggleAttribute("data-current", n === index));
    position.textContent = `第 ${index + 1} 張，共 ${cards.length} 張`;
    // A button that has just reached its end keeps the focus from falling to the page.
    const focused = root.ownerDocument.activeElement;
    prev.disabled = index === 0;
    next.disabled = index === last;
    if (focused?.disabled) (focused === prev ? next : prev).focus();
    // So does a card going behind: the focus moves to the one coming to the front.
    else if (cards.some((card) => card.inert && card.contains(focused))) {
      cards[index].querySelector("a, button")?.focus();
    }
    cards[index].dispatchEvent(new Event("card-stack-show", { bubbles: true }));
  }

  prev.addEventListener("click", () => show(index - 1));
  next.addEventListener("click", () => show(index + 1));
  root.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") show(index - 1);
    else if (event.key === "ArrowRight") show(index + 1);
    else return;
    event.preventDefault();
  });

  let startX = null;
  let moved = false;

  function follow(dx) {
    if (reduced) return;
    root.style.setProperty("--card-stack-drag", `${dx}px`);
    root.toggleAttribute("data-dragging", true);
  }

  function release() {
    startX = null;
    root.style.removeProperty("--card-stack-drag");
    root.removeAttribute("data-dragging");
  }

  track.addEventListener("pointerdown", (event) => {
    startX = event.clientX;
    moved = false;
  });
  track.addEventListener("pointermove", (event) => {
    // No button held: a press let go off the cards, before the drag held the pointer.
    if (startX === null || event.buttons === 0) return;
    let dx = event.clientX - startX;
    // Held only once it is a drag: a captured pointer's click goes to the track, not the link
    // tapped.
    if (!moved && Math.abs(dx) > MOVED) {
      moved = true;
      track.setPointerCapture?.(event.pointerId);
    }
    // Past either end the card gives a little, then stops.
    if ((index === 0 && dx > 0) || (index === last && dx < 0)) dx /= 3;
    if (moved) follow(dx);
  });
  track.addEventListener("pointerup", (event) => {
    if (startX === null) return;
    const dx = event.clientX - startX;
    release();
    if (dx <= -DRAG_THRESHOLD) show(index + 1);
    else if (dx >= DRAG_THRESHOLD) show(index - 1);
  });
  track.addEventListener("pointercancel", release);
  // The click a drag ends with is not a tap on the card's 開始作答.
  track.addEventListener(
    "click",
    (event) => {
      if (!moved) return;
      moved = false;
      event.preventDefault();
      event.stopPropagation();
    },
    true,
  );
  // A link dragged by a mouse would otherwise drag its address instead of the card.
  track.addEventListener("dragstart", (event) => event.preventDefault());

  root.querySelector(".card-stack-controls").hidden = false;
  root.toggleAttribute("data-ready", true);
  show(0);
}
