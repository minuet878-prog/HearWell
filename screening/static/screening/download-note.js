// Account page, the feedback batch (the owner's F4 B, words as the owner finalised them): a press
// of 下載我的資料 starts a download and the page would not change, so its line says it has
// started and where the file goes, in the success green with a tick, as ✓ 已複製 does. The page
// cannot know the file was kept, so "started". It stays until the page is left: the site's done
// notes do not fade by themselves (F1). Screen readers hear it in the status area, each press anew
// (emptied first: the same words written over themselves are not read again). Without
// JavaScript the row is as before.
(function () {
  const link = document.querySelector("[data-download-note]");
  if (!link) return;
  const words = link.querySelector("[data-download-words]");
  const status = document.querySelector("[data-download-status]");
  const started = "已開始下載，請到手機的「下載項目」找。";
  link.addEventListener("click", () => {
    link.classList.add("is-download-started");
    link.querySelector(".action-card-icon").innerHTML =
      '<svg viewBox="0 0 24 24" focusable="false"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
    words.textContent = `✓ ${started}`;
    status.textContent = "";
    setTimeout(() => {
      status.textContent = started;
    }, 100);
  });
})();
