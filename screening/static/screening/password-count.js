// Readability batch 3 (the owner's C1 B): under a new password, how many characters are in and,
// short of the minimum, how many are still missing; a tick once there are enough. Only the count:
// #332 left whether a password is good enough to the server, so the rules under it stay words.
// Without JavaScript the line stays hidden. The line is not read out as it changes; screen
// readers hear the count once typing pauses (as GOV.UK's character count does), not at each key.
(function () {
  document.querySelectorAll(".password-count").forEach((line) => {
    const input = document.getElementById(line.dataset.for);
    const status = line.parentElement.querySelector(".password-count-status");
    const min = Number(line.dataset.min);
    let pause;

    function count() {
      // As Django's MinimumLengthValidator counts, len() of the password: an emoji is one.
      const typed = Array.from(input.value).length;
      const words =
        typed >= min ? `✓ 已經輸入 ${typed} 個字` : `已經輸入 ${typed} 個字，還差 ${min - typed} 個`;
      line.hidden = typed === 0;
      line.textContent = typed === 0 ? "" : words;
      line.classList.toggle("is-enough", typed >= min);
      clearTimeout(pause);
      pause = setTimeout(() => {
        status.textContent = line.textContent;
      }, 1000);
    }

    input.addEventListener("input", count);
    // A password the browser filled in is counted on arrival (the server never sends one back).
    if (input.value) count();
  });
})();
