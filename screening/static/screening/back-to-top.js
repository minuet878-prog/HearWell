// #335 (spec #326 E1): 回到頂端 on the long pages, once they have scrolled past one screen. The
// button starts hidden, so without JavaScript it never shows.
(function () {
  const button = document.getElementById("back-to-top");
  const tabBar = document.querySelector(".site-nav");
  if (!button) return;

  function update() {
    button.hidden = window.scrollY <= window.innerHeight;
    // On phones the button sits above the fixed tab bar (site.css), whose height grows with the
    // text size.
    button.style.setProperty("--tab-bar-height", tabBar.offsetHeight + "px");
  }

  button.addEventListener("click", function () {
    // "auto" follows the CSS, which scrolls smoothly only without reduced motion (site.css).
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    // Focus moves to the page title, so keyboard and screen reader users start from the top too;
    // preventScroll keeps the focus from cutting the smooth scroll short.
    const heading = document.querySelector("main h1");
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  });
  window.addEventListener("scroll", update, { passive: true });
  update();
})();
