// The home-screen app has no browser toolbar: no back button on an iPhone, no pull to
// refresh on either phone (spec docs/specs/phase-10/phase10_pwa_back_refresh.md).
export const PULL_THRESHOLD = 80;
const HOME = "/";

const isStandalone = (win) =>
  win.navigator.standalone === true || win.matchMedia?.("(display-mode: standalone)").matches;

// Reloading would throw away whatever was typed or picked, so pages with inputs opt out.
const hasInputs = (doc) => doc.querySelector("main :is(form, input, select, textarea)") !== null;

// history.length can count entries the app cannot go back to (after an iPhone reloads a
// page from the background); canGoBack does not. Older iPhones lack the Navigation API.
function goBack(win) {
  const canGoBack = win.navigation?.canGoBack ?? win.history.length > 1;
  if (canGoBack) win.history.back();
  else win.location.assign(HOME);
}

function setUpPullToRefresh(win) {
  const hint = win.document.getElementById("pwa-pull");
  let startY = null;
  let pulled = 0;
  const reset = () => {
    startY = null;
    hint.hidden = true;
  };

  // Pinching or panning a zoomed page is not a pull.
  const isPull = (event) =>
    event.touches.length === 1 &&
    !(win.visualViewport?.scale > 1) &&
    win.scrollY <= 0 &&
    !hasInputs(win.document);

  win.addEventListener("touchstart", (event) => {
    pulled = 0;
    startY = isPull(event) ? event.touches[0].clientY : null;
  }, { passive: true });
  win.addEventListener("touchmove", (event) => {
    if (startY === null) return;
    if (event.touches.length > 1) {
      reset();
      return;
    }
    pulled = event.touches[0].clientY - startY;
    hint.hidden = pulled <= 0;
    hint.textContent = pulled >= PULL_THRESHOLD ? "放開重新整理" : "往下拉重新整理";
  }, { passive: true });
  win.addEventListener("touchend", () => {
    if (startY !== null && pulled >= PULL_THRESHOLD) win.location.reload();
    reset();
  });
  win.addEventListener("touchcancel", reset);
}

export function setUpPwaNav(win = window) {
  if (!isStandalone(win)) return;
  const back = win.document.getElementById("pwa-back");
  if (back) {
    back.hidden = false;
    back.addEventListener("click", () => goBack(win));
  }
  setUpPullToRefresh(win);
}
