// Register page (#332, spec #326 D6): a green tick inside 出生年 and 密碼確認 once they are
// right, and the words in the field's status area for screen readers. Nothing is said when
// they are not: mistakes are still the server's to show. 密碼 itself gets no tick; only the
// server can say it is good enough.
(function () {
  const year = document.getElementById("id_roc_birth_year");
  const password = document.getElementById("id_password1");
  const confirmation = document.getElementById("id_password2");

  // site.css draws the tick inside the field's right end; inside the field, it stays there
  // however narrow the row gets at double text size.
  // `answers` picks the server's errors the tick answers (field_messages.html marks each line
  // with Django's error code); without it, the tick answers them all.
  function show(input, right, words, answers = ".field-error") {
    input.classList.toggle("is-right", right);
    const status = input.closest(".auth-field").querySelector('[role="status"]');
    const text = right ? words : "";
    // Only on a change, so typing on in a right field does not repeat the words.
    if (status.textContent !== text) status.textContent = text;
    if (right) clearServerError(input, answers);
  }

  // Once the tick shows, the server's words it answers go, and with the field's last one its red
  // frame (owner's call, 2026-10-24); going wrong again does not bring them back: the server says
  // so on sending.
  function clearServerError(input, answers) {
    const errorId = `${input.id}_error`;
    const box = document.getElementById(errorId);
    if (!box) return;
    box.querySelectorAll(answers).forEach((line) => line.remove());
    if (box.querySelector(".field-error")) return;
    box.remove();
    input.removeAttribute("aria-invalid");
    const described = (input.getAttribute("aria-describedby") || "")
      .split(" ")
      .filter((id) => id && id !== errorId)
      .join(" ");
    if (described) input.setAttribute("aria-describedby", described);
    else input.removeAttribute("aria-describedby");
  }

  // The server's rule (RegisterForm.clean_roc_birth_year), whose latest year the page gives:
  // whole digits, spaces around trimmed, full-width digits read as digits, 1 to the latest.
  function checkYear() {
    const digits = year.value
      .trim()
      .replace(/[０-９]/g, (d) => String.fromCharCode(d.charCodeAt(0) - 0xfee0));
    const value = Number(digits);
    show(year, /^[0-9]+$/.test(digits) && value >= 1 && value <= Number(year.dataset.max), "格式正確");
  }

  function checkConfirmation() {
    const same = confirmation.value !== "" && confirmation.value === password.value;
    // Only 「兩次密碼不一致」: what the server said about the password itself still stands.
    show(confirmation, same, "兩次密碼相同", '[data-code="password_mismatch"]');
  }

  year.addEventListener("input", checkYear);
  password.addEventListener("input", checkConfirmation);
  confirmation.addEventListener("input", checkConfirmation);
  // A year the server kept after a mistake elsewhere on the form is checked on arrival.
  checkYear();
  checkConfirmation();
})();
