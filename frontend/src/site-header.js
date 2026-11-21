// #748 (ADR 0079): a round ‹ before 聽伴 on every page but the home page (the owner, 2026-11-21).
// Scrolled past the header, 聽伴 goes and the ‹ and the avatar turn frosted (site.css, by
// data-scrolled); back at the top they are as before. The ‹ is a link
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

  // The answer page has 離開 in its place (#755): there going back would be the previous question.
  if (back && canGoBackInSite(win)) {
    back.setAttribute("aria-label", "回上一頁");
    back.addEventListener("click", (event) => {
      event.preventDefault();
      win.history.back();
    });
  }
}

// Spec #741 at acceptance (2026-11-21, compare-avatar-menu.html A): signed in, tapping the avatar
// opens a small menu of 帳號設定 and 登出. layout.html has both the avatar as a link to account
// settings (without JavaScript) and the menu button, hidden; here the button takes the link's
// place. A disclosure button (aria-expanded, aria-controls), not an ARIA menu: Tab and Enter
// reach the two items as on the rest of the page, with no arrow keys to learn.
export function setUpAccountMenu(doc = document) {
  const account = doc.querySelector("[data-site-account]");
  if (!account) return;
  const link = account.querySelector("a.site-avatar");
  const avatar = account.querySelector("[data-site-account-toggle]");
  const menu = doc.getElementById(avatar.getAttribute("aria-controls"));
  link.hidden = true;
  avatar.hidden = false;

  const setOpen = (open) => {
    menu.hidden = !open;
    avatar.setAttribute("aria-expanded", String(open));
  };

  avatar.addEventListener("click", () => {
    if (menu.hidden) {
      setOpen(true);
      menu.querySelector("a, button").focus();
    } else {
      setOpen(false);
      avatar.focus();
    }
  });

  // A tap outside closes it: pointerdown, as an iPhone sends no click to the page for a tap on
  // plain text. The focus, if still in the menu, would be lost in it hidden: back to the avatar.
  doc.addEventListener("pointerdown", (event) => {
    if (menu.hidden || account.contains(event.target)) return;
    setOpen(false);
    if (menu.contains(doc.activeElement)) avatar.focus();
  });

  doc.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || menu.hidden) return;
    setOpen(false);
    avatar.focus();
  });
}
