// Copy buttons. Where the browser can copy, a button copies its words and says 已複製; without
// JavaScript, or where it cannot, the button stays hidden and what it would copy is on the
// page to copy by hand.
// #332 (spec #326 B3): the button itself turns green with ✓ 已複製 for 2 seconds, and every
// press writes 已複製 into a status area anew, so a screen reader says it each time.
// Share page (#193): 複製連結 (#copy-link) copies the link and hides the written address.
// #366 (spec #354): without the phone's share sheet (share-button.js keeps its button hidden),
// copying is the way to send, so that button becomes the solid main one.
// #361: the family page's 複製網址 (data-without-share-sheet) shows only where the phone's share
// sheet is not; its address has no id="share-url" and stays on the page above the button.
// 傳給他 (spec #655): its 複製訊息 is also data-without-share-sheet, and copies data-text, the
// message with the address, which the page shows above it. It keeps the style its page gave it.
// #580 (spec #576): 複製信箱 (data-copy, the address to copy) in every page's footer and beside
// the account page's sentence; several on a page, each its own, saying 已複製 in the footer's
// status area (data-copy-status). One the browser refuses goes away, so no button does
// nothing; the address is still beside it.
(function () {
  if (!navigator.clipboard || !window.isSecureContext) return;
  const tick =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';

  // Shows button; a press copies text and says so on the button and in status, or, when the
  // browser refuses, calls onRefused.
  function showCopyButton(button, text, status, onRefused) {
    const label = button.innerHTML;
    let timer;
    button.hidden = false;
    button.addEventListener("click", () => {
      navigator.clipboard.writeText(text).then(() => {
        button.classList.add("is-copied");
        button.innerHTML = tick + "已複製";
        // Emptied first and written a moment later: the same words written straight over
        // themselves are not read again.
        status.textContent = "";
        setTimeout(() => { status.textContent = "已複製"; }, 100);
        clearTimeout(timer);
        timer = setTimeout(() => {
          button.classList.remove("is-copied");
          button.innerHTML = label;
        }, 2000);
      }, onRefused);
    });
  }

  const linkButton = document.getElementById("copy-link");
  if (linkButton && !("withoutShareSheet" in linkButton.dataset && navigator.share)) {
    const address = document.getElementById("share-url");
    if (address) address.hidden = true;
    const withoutShareSheet = "withoutShareSheet" in linkButton.dataset;
    if (!navigator.share && !withoutShareSheet) {
      linkButton.classList.replace("btn-outline-primary", "btn-primary");
    }
    const words = linkButton.dataset.text ?? linkButton.dataset.url;
    showCopyButton(linkButton, words, document.getElementById("copy-status"), () => {
      if (address) address.hidden = false;
    });
  }

  const addressStatus = document.querySelector("[data-copy-status]");
  for (const button of document.querySelectorAll("[data-copy]")) {
    showCopyButton(button, button.dataset.copy, addressStatus, () => { button.hidden = true; });
  }
})();
