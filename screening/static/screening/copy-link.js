// Share page (#193): where the browser can copy, a button copies the link and says 已複製;
// without JavaScript, or where it cannot, the address stays on the page to copy by hand.
// #332 (spec #326 B3): the button itself turns green with ✓ 已複製 for 2 seconds, and every
// press writes 已複製 into the status area anew, so a screen reader says it each time.
(function () {
  const button = document.getElementById("copy-link");
  const address = document.getElementById("share-url");
  const status = document.getElementById("copy-status");
  if (!button || !navigator.clipboard || !window.isSecureContext) return;
  const words = button.textContent;
  const tick =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
  let timer;
  button.hidden = false;
  address.hidden = true;
  button.addEventListener("click", () => {
    navigator.clipboard.writeText(button.dataset.url).then(
      () => {
        button.classList.add("is-copied");
        button.innerHTML = tick + "已複製";
        // Emptied first and written a moment later: the same words written straight over
        // themselves are not read again.
        status.textContent = "";
        setTimeout(() => { status.textContent = "已複製"; }, 100);
        clearTimeout(timer);
        timer = setTimeout(() => {
          button.classList.remove("is-copied");
          button.textContent = words;
        }, 2000);
      },
      () => { address.hidden = false; },
    );
  });
})();
