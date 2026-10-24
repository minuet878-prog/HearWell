// Register page (#151): the 顯示 button lets people check what they typed. It is hidden in the
// page and only shown here, so without JavaScript nobody sees a button that does nothing.
// #332 (spec #326 D5): an open eye beside 顯示, a slashed eye beside 隱藏; the icons are not
// read out, so the button's name stays the same.
const PASSWORD_EYES = {
  顯示: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
  隱藏: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M3 3l18 18"/><path d="M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3 3.8M6.6 6.6C3.9 8.4 2 12 2 12s3.5 7 10 7a9.6 9.6 0 0 0 4.4-1"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>',
};
document.querySelectorAll(".password-toggle").forEach((button) => {
  const input = document.getElementById(button.getAttribute("aria-controls"));
  button.innerHTML = PASSWORD_EYES.顯示 + "顯示";
  button.hidden = false;
  button.addEventListener("click", () => {
    const show = input.type === "password";
    const action = show ? "隱藏" : "顯示";
    input.type = show ? "text" : "password";
    button.innerHTML = PASSWORD_EYES[action] + action;
    button.setAttribute("aria-label", action + button.dataset.label);
  });
});
