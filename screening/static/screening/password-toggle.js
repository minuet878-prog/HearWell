// Register page (#151): the 顯示 button lets people check what they typed. It is hidden in the
// page and only shown here, so without JavaScript nobody sees a button that does nothing.
document.querySelectorAll(".password-toggle").forEach((button) => {
  const input = document.getElementById(button.getAttribute("aria-controls"));
  button.hidden = false;
  button.addEventListener("click", () => {
    const show = input.type === "password";
    const action = show ? "隱藏" : "顯示";
    input.type = show ? "text" : "password";
    button.textContent = action;
    button.setAttribute("aria-label", action + button.dataset.label);
  });
});
