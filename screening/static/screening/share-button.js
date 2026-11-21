// Family guide and report sharing (specs phase8_c1_family_guide.md, phase8_c1_family_share.md):
// the button appears only where the phone's share sheet exists; everywhere else the copy button
// (copy-link.js) is the way to send (#741: no address is written on the page any more).
// data-url/data-title share another page than this one.
// 傳給他 (spec #655): data-text is the whole message with the address in it, sent as one text,
// since some apps keep only the address when given a text and an address apart.
(function () {
  const button = document.getElementById("share-button");
  if (!button || !navigator.share) return;
  button.hidden = false;
  button.addEventListener("click", () => {
    // Closing the share sheet rejects the promise; that is not an error for the user.
    const { text, url = location.href, title = document.title } = button.dataset;
    navigator.share(text ? { text } : { title, url }).catch(() => {});
  });
})();
