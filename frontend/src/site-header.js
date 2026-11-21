// #748 (ADR 0079): scrolled past the header, 聽伴 gives way to a round frosted ‹ and the avatar
// turns frosted (site.css, by data-scrolled); back at the top they swap again. The ‹ is a link
// home in the page, so it still works without JavaScript; here it goes back instead when the
// page before this one is of this site. This took over the home-screen app's own 上一頁.

// The Navigation API's canGoBack counts only this site's pages. Browsers without it: a history
// to go back in, and this site named as where the page came from.
function canGoBackInSite(win) {
  if (win.navigation) return win.navigation.canGoBack;
  const referrer = win.document.referrer;
  return win.history.length > 1 && referrer.startsWith(`${win.location.origin}/`);
}

export function setUpSiteHeader(win = window) {
  const header = win.document.querySelector(".site-header");
  const back = header.querySelector("[data-site-back]");

  const update = () => header.toggleAttribute("data-scrolled", win.scrollY > header.offsetHeight);
  update();
  win.addEventListener("scroll", update, { passive: true });

  if (canGoBackInSite(win)) {
    back.setAttribute("aria-label", "回上一頁");
    back.addEventListener("click", (event) => {
      event.preventDefault();
      win.history.back();
    });
  }
}
