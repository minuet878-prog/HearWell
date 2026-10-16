// Family guide (spec docs/specs/phase8_c1_family_guide.md): the button appears only where the
// phone's share sheet exists; everywhere else the address shown on the page is the fallback.
(function () {
  const button = document.getElementById("share-button");
  if (!button || !navigator.share) return;
  button.hidden = false;
  button.addEventListener("click", () => {
    // Closing the share sheet rejects the promise; that is not an error for the user.
    navigator.share({ title: document.title, url: location.href }).catch(() => {});
  });
})();
