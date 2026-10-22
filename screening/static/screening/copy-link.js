// Share page (#193): where the browser can copy, a button copies the link and says 已複製;
// without JavaScript, or where it cannot, the address stays on the page to copy by hand.
(function () {
  const button = document.getElementById("copy-link");
  const address = document.getElementById("share-url");
  const status = document.getElementById("copy-status");
  if (!button || !navigator.clipboard || !window.isSecureContext) return;
  button.hidden = false;
  address.hidden = true;
  button.addEventListener("click", () => {
    navigator.clipboard.writeText(button.dataset.url).then(
      () => { status.textContent = "已複製"; },
      () => { address.hidden = false; },
    );
  });
})();
