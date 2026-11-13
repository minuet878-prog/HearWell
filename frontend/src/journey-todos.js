// #481 (spec #478): a 手動待辦 ticked or unticked without leaving the page, the home page's
// 現在這一步 card and my guide's 您在這裡 card alike. Each row is a form (journey_todos.html),
// which without JavaScript saves and comes back to the row; here it is sent asking for JSON, and
// ✓ 已儲存 shows beside the row as on the answer page (#326 B4, ADR 0028), unticking too (the
// owner's D4 on #479).

// As long as the answer page's (AnswerApp.jsx); site.css fades it in its last 0.3 s.
export const SAVED_FOR = 1500;
const TICK = "M5 12.5l4.5 4.5L19 7.5";
const SVG = "http://www.w3.org/2000/svg";

export function tickInPlace(doc = document, win = window) {
  let saved = null;
  let timer = null;

  const say = (button) => {
    saved?.remove();
    win.clearTimeout(timer);
    saved = doc.createElement("span");
    saved.className = "todo-saved";
    // Not read out: the checkbox says its new state itself.
    saved.setAttribute("aria-hidden", "true");
    saved.textContent = "✓ 已儲存";
    button.append(saved);
    timer = win.setTimeout(() => saved?.remove(), SAVED_FOR);
  };

  const show = (form, ticked) => {
    const button = form.querySelector("button");
    const box = form.querySelector(".todo-box");
    form.closest(".todo").classList.toggle("is-done", ticked);
    button.setAttribute("aria-checked", String(ticked));
    form.elements.ticked.value = ticked ? "0" : "1";
    box.replaceChildren();
    if (ticked) {
      // Drawn once, being just ticked (the mockup's note ⑧); with reduced motion simply there.
      const svg = doc.createElementNS(SVG, "svg");
      svg.setAttribute("viewBox", "0 0 24 24");
      svg.setAttribute("focusable", "false");
      svg.classList.add("todo-tick");
      const path = doc.createElementNS(SVG, "path");
      path.setAttribute("pathLength", "1");
      path.setAttribute("d", TICK);
      svg.append(path);
      box.append(svg);
    }
    say(button);
  };

  // Caught before page-loading.js hears of it (a capturing listener), which would take it for a
  // page to wait for and put 送出中… in the button in place of the box.
  const capture = true;
  doc.addEventListener(
    "submit",
    async (event) => {
      const form = event.target.closest("[data-todo-tick]");
      if (!form) return;
      event.preventDefault();
      if (form.dataset.sending) return; // a second press before the first is saved
      form.dataset.sending = "true";
      let reply;
      try {
        const response = await win.fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: { Accept: "application/json" },
          // Signed out meanwhile, the login page would come back as if saved.
          redirect: "manual",
        });
        if (!response.ok) throw new Error(`not saved: ${response.status}`);
        reply = await response.json();
      } catch {
        // Sent the plain way, the server says what happened: the login page, or the row.
        form.submit();
        return;
      } finally {
        delete form.dataset.sending;
      }
      show(form, reply.ticked);
    },
    capture,
  );
}
