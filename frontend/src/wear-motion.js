// 看動作 (spec #519, tickets #521 and #522; ADR 0060): the 怎麼戴上、拿下 drawings that carry a
// data-motion get a button under them that plays the motion once. Without JavaScript or with
// reduced motion there is no button and the drawing is the reviewed one, arrows and all.
//
// data-motion (wear-motion-review.md's table) counts the pieces of the drawing, the children of
// its outer scale group, from 0:
//   parts: pieces that move together, each key [percent of the play, right, down, clockwise
//     degrees about pivot]; before the first key they wait at it, after the last they stay.
//   lines: pieces whose points (pairs of numbers in d, from 0) go where part `with` takes them.
//   shapes: pieces whose d starts as `from` and becomes the reviewed one as part `with` moves.
// cues: the arrows, gone while and after it plays.

const NUMBER = /-?\d+(?:\.\d+)?/g;

const round = (n) => String(Math.round(n * 100) / 100);

// The drawing as reviewed, before any play changed it.
const reviewed = new WeakMap();

function reviewedPieces(drawing) {
  if (!reviewed.has(drawing)) {
    const pieces = [...drawing.firstElementChild.children];
    reviewed.set(
      drawing,
      pieces.map((piece) => ({
        transform: piece.getAttribute("transform"),
        d: piece.getAttribute("d"),
      })),
    );
  }
  return reviewed.get(drawing);
}

const DURATION = 2400;

// The mockup's easing, slow out of one key and slow into the next.
const ease = (t) => (t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2);

// Where a part is at percent: [right, down, degrees].
function pose(keys, percent) {
  if (percent <= keys[0][0]) return keys[0].slice(1);
  for (let i = 1; i < keys.length; i++) {
    const [from, to] = [keys[i - 1], keys[i]];
    if (percent < to[0]) {
      const t = ease((percent - from[0]) / (to[0] - from[0]));
      return [1, 2, 3].map((j) => from[j] + (to[j] - from[j]) * t);
    }
  }
  return keys.at(-1).slice(1);
}

const still = (where) => where.every((n) => n === 0);

function movePoint([x, y], [right, down, degrees], [px, py]) {
  const turn = (degrees * Math.PI) / 180;
  const dx = x - px;
  const dy = y - py;
  return [
    px + dx * Math.cos(turn) - dy * Math.sin(turn) + right,
    py + dx * Math.sin(turn) + dy * Math.cos(turn) + down,
  ];
}

function draw(drawing, percent) {
  const motion = JSON.parse(drawing.dataset.motion);
  const pieces = [...drawing.firstElementChild.children];
  const original = reviewedPieces(drawing);
  const poses = motion.parts.map((part) => pose(part.keys, percent));
  motion.parts.forEach((part, i) => {
    const [right, down, degrees] = poses[i];
    const [px, py] = part.pivot;
    for (const index of part.pieces) {
      const before = original[index].transform;
      // Where it is drawn, it is drawn as reviewed, to the character.
      if (still(poses[i])) {
        if (before) pieces[index].setAttribute("transform", before);
        else pieces[index].removeAttribute("transform");
        continue;
      }
      const moved = `translate(${round(right)} ${round(down)}) rotate(${round(degrees)} ${px} ${py})`;
      pieces[index].setAttribute("transform", before ? `${moved} ${before}` : moved);
    }
  });
  for (const line of motion.lines || []) {
    const part = motion.parts[line.with];
    for (const index of line.pieces) {
      if (still(poses[line.with])) {
        pieces[index].setAttribute("d", original[index].d);
        continue;
      }
      const numbers = original[index].d.match(NUMBER).map(Number);
      for (const point of line.points) {
        const [x, y] = movePoint(numbers.slice(point * 2, point * 2 + 2), poses[line.with], part.pivot);
        numbers[point * 2] = x;
        numbers[point * 2 + 1] = y;
      }
      let n = 0;
      pieces[index].setAttribute(
        "d",
        original[index].d.replace(NUMBER, () => round(numbers[n++])),
      );
    }
  }
  for (const shape of motion.shapes || []) {
    const { keys } = motion.parts[shape.with];
    const [first, last] = [keys[0][0], keys.at(-1)[0]];
    const t = ease(Math.min(Math.max((percent - first) / (last - first), 0), 1));
    for (const index of shape.pieces) {
      if (t === 1) {
        pieces[index].setAttribute("d", original[index].d);
        continue;
      }
      const to = original[index].d.match(NUMBER).map(Number);
      let n = 0;
      pieces[index].setAttribute(
        "d",
        shape.from.replace(NUMBER, (from) => round(Number(from) + (to[n++] - from) * t)),
      );
    }
  }
  for (const index of motion.cues) pieces[index].setAttribute("visibility", "hidden");
}

// Seen as ▶ 看動作; heard with the step's title, 看動作：推進耳塞, so a row of them is not a row
// of 看動作. The label starts with the words seen, for those who speak to their phone.
function say(button, icon, words) {
  button.textContent = `${icon} ${words}`;
  button.setAttribute("aria-label", `${words}：${button.dataset.motionPlay}`);
}

// The frame each drawing is waiting for, so 再看一次 while it plays starts it over.
const frames = new WeakMap();

function play(win, button) {
  const drawing = button.previousElementSibling;
  win.cancelAnimationFrame(frames.get(drawing));
  const start = win.performance.now();
  const frame = () => {
    const elapsed = win.performance.now() - start;
    draw(drawing, Math.min(elapsed / DURATION, 1) * 100);
    if (elapsed < DURATION) {
      frames.set(drawing, win.requestAnimationFrame(frame));
    } else {
      say(button, "↺", "再看一次");
    }
  };
  frame();
}

export function addMotionButtons(win = window) {
  if (win.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  for (const drawing of win.document.querySelectorAll("svg[data-motion]")) {
    // The step's title is the bold line of its box (care_step.html), after its number.
    const title = drawing
      .closest("li")
      .querySelector("label strong")
      .textContent.replace(/^\d+\.\s*/, "");
    const button = win.document.createElement("button");
    button.type = "button";
    button.className = "btn btn-outline-primary care-motion-play";
    button.dataset.motionPlay = title;
    say(button, "▶", "看動作");
    drawing.after(button);
  }
  // One listener for the page, so the steps pick-explain.js copies play too.
  win.document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-motion-play]");
    if (button) play(win, button);
  });
}
