// Family guide and report sharing (specs phase8_c1_family_guide.md, phase8_c1_family_share.md):
// the button appears only where the phone's share sheet exists; everywhere else the address
// shown on the page is the fallback. data-url/data-title share another page than this one.
(function () {
  const button = document.getElementById("share-button");
  if (!button || !navigator.share) return;
  button.hidden = false;
  button.addEventListener("click", () => {
    // Closing the share sheet rejects the promise; that is not an error for the user.
    const { url = location.href, title = document.title } = button.dataset;
    navigator.share({ title, url }).catch(() => {});
  });
})();
