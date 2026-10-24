// Spec #338 (ticket #344): above each box that scrolls sideways (.scroll-box), a line saying so,
// shown only while the table is wider than its box. Made here, so there is none without
// JavaScript; the shadows at the box's edges are CSS alone.
export function setUpScrollHint(win = window) {
  const doc = win.document;
  const pairs = [...doc.querySelectorAll(".scroll-box")].map((box) => {
    const hint = doc.createElement("p");
    hint.className = "scroll-hint";
    hint.textContent = "表格可以左右滑動";
    hint.hidden = true;
    box.before(hint);
    return [box, hint];
  });

  // The box changes size with the screen's width and when its fold opens; the table inside with
  // the text size. Either way, decide again.
  const observer = new win.ResizeObserver(() => {
    for (const [box, hint] of pairs) hint.hidden = box.scrollWidth <= box.clientWidth;
  });
  for (const [box] of pairs) {
    observer.observe(box);
    observer.observe(box.firstElementChild);
  }
}
