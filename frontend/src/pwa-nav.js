// The home-screen app has no browser toolbar: no back button on an iPhone, no pull to
// refresh on either phone (spec docs/specs/phase-10/phase10_pwa_back_refresh.md). Its back
// button became every page's ‹ in the header (#748, site-header.js).
export const PULL_THRESHOLD = 80;
export const PULL_SHOW_AFTER = 16;

const isStandalone = (win) =>
  win.navigator.standalone === true || win.matchMedia?.("(display-mode: standalone)").matches;

// Reloading would throw away whatever was typed or picked, so pages with inputs opt out.
const hasInputs = (doc) => doc.querySelector("main :is(form, input, select, textarea)") !== null;

function setUpPullToRefresh(win) {
  const hint = win.document.getElementById("pwa-pull");
  let startY = null;
  let startX = null;
  let pulled = 0;
  const reset = () => {
    startY = null;
    startX = null;
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
    if (isPull(event)) {
      startY = event.touches[0].clientY;
      startX = event.touches[0].clientX;
    } else {
      startY = null;
      startX = null;
    }
  }, { passive: true });
  win.addEventListener("touchmove", (event) => {
    if (startY === null) return;
    if (event.touches.length > 1) {
      reset();
      return;
    }
    const touch = event.touches[0];
    pulled = touch.clientY - startY;
    if (Number.isFinite(startX) && Number.isFinite(touch.clientX)) {
      const dx = Math.abs(touch.clientX - startX);
      if (dx > 10 && dx > Math.abs(pulled)) {
        reset();
        return;
      }
    }
    hint.hidden = pulled < PULL_SHOW_AFTER;
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
  // The iPhone home-screen app keeps its own cookies, apart from Safari's: the server reads
  // this one when a LINE trip starts (screening/oidc.py HOME_SCREEN_APP). Written again on
  // every page, as an iPhone keeps a cookie a script wrote for 7 days.
  if (win.navigator.standalone === true) {
    win.document.cookie = "home_screen_app=1; path=/; max-age=31536000; samesite=lax";
  }
  // Ticket #160: e.g. the home page's "加到手機主畫面"; without JavaScript they stay.
  for (const item of win.document.querySelectorAll("[data-hide-in-app]")) item.hidden = true;
  setUpPullToRefresh(win);
}
