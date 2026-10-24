// Waiting for the next page shows nothing, and many people press again. Chosen by the site owner
// on the loading comparison page: A3, a bar along the top with 載入中…, and C1, 送出中… with a
// spinner on the pressed button of a form that saves something. Moving parts wait 0.3 s (site.css).
export const SHOW_AFTER = 300;
// Same as the answer form had (spec docs/specs/phase-06/phase6_web_double_submit.md 4.2): the
// server refuses a second save, so giving the button back is always safe.
export const GIVE_BACK_AFTER = 10000;
const LOADING = "載入中…";
const SENDING = "送出中…";

// Links the browser opens as a new page in this tab: not downloads, other sites or jumps within
// this page, which leave the page where it is.
function opensPage(event, link, win) {
  if (event.defaultPrevented || event.button !== 0) return false;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false;
  if (link.hasAttribute("download") || (link.target && link.target !== "_self")) return false;
  const here = new URL(win.location.href);
  const url = new URL(link.getAttribute("href"), here);
  if (url.origin !== here.origin) return false;
  return !(url.hash && url.pathname === here.pathname && url.search === here.search);
}

export function setUpPageLoading(win) {
  const doc = win.document;
  const status = doc.getElementById("page-loading-status");
  let showTimer;
  let giveBackTimer;
  let sending = null; // { form, button, label }

  function reset() {
    win.clearTimeout(showTimer);
    win.clearTimeout(giveBackTimer);
    doc.documentElement.classList.remove("page-loading");
    status.textContent = "";
    if (sending) {
      sending.button.disabled = false;
      sending.button.replaceChildren(...sending.label);
      sending = null;
    }
  }

  function wait() {
    reset();
    showTimer = win.setTimeout(() => {
      doc.documentElement.classList.add("page-loading");
      status.textContent ||= LOADING;
    }, SHOW_AFTER);
    giveBackTimer = win.setTimeout(reset, GIVE_BACK_AFTER);
  }

  doc.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (link && opensPage(event, link, win)) wait();
  });

  doc.addEventListener("submit", (event) => {
    if (event.defaultPrevented) return;
    const form = event.target;
    if (form === sending?.form) {
      event.preventDefault();
      return;
    }
    wait();
    // Only forms that save something; the header's 登出 just gets the bar.
    if (form.method !== "post" || !form.closest("main")) return;
    const button = event.submitter;
    sending = { form, button, label: [...button.childNodes] };
    const spinner = doc.createElement("span");
    spinner.className = "spinner";
    spinner.setAttribute("aria-hidden", "true");
    button.replaceChildren(spinner, SENDING);
    status.textContent = SENDING;
    // The browser reads the pressed button's name and value (consent's agree) right after this
    // event and skips disabled buttons, so disable it a moment later.
    win.setTimeout(() => {
      button.disabled = true;
    }, 0);
  });

  // The back button can bring this page back from cache still waiting.
  win.addEventListener("pageshow", reset);
}
