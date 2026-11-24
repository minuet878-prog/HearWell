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

  // C6: live character count for maximum-length fields (e.g. feedback text), replacing the static
  // help text while characters are typed and announcing to screen readers after a 1s pause.
  document.querySelectorAll(".feedback-count").forEach((line) => {
    const input = document.getElementById(line.dataset.for);
    const help = document.getElementById(line.dataset.help);
    const status = line.parentElement.querySelector(".feedback-count-status");
    const max = Number(line.dataset.max).toLocaleString("en-US");
    let pause;

    function count() {
      const typed = Array.from(input.value).length;
      const words = typed === 0 ? "" : `已輸入 ${typed.toLocaleString("en-US")} / ${max} 字`;
      line.hidden = typed === 0;
      if (help) help.hidden = typed > 0;
      line.textContent = words;
      clearTimeout(pause);
      pause = setTimeout(() => {
        status.textContent = words;
      }, 1000);
    }

    input.addEventListener("input", count);
    if (input.value) count();
  });
})();
