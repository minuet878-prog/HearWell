// Web answer form: once "送出" is pressed it says so and cannot be pressed again, because many
// people press twice when nothing seems to happen. The server already refuses a second save
// (spec docs/specs/phase-06/phase6_web_double_submit.md), so giving the button back is always safe.
(function () {
  const form = document.getElementById("answer-form");
  const button = form && form.querySelector('[type="submit"]');
  const status = document.getElementById("submit-status");
  if (!button || !status) return;
  const label = button.value;
  let timer;

  function reset() {
    clearTimeout(timer);
    button.disabled = false;
    button.value = label;
    status.textContent = "";
  }

  form.addEventListener("submit", function () {
    // The browser has already taken this submit, so disabling the button does not cancel it.
    button.disabled = true;
    button.value = "送出中…";
    status.textContent = "送出中…";
    timer = setTimeout(reset, 10000);
  });
  // The back button can restore this page from cache with the button still disabled.
  window.addEventListener("pageshow", reset);
})();
