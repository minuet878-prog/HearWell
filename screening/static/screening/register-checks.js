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
  function show(input, right, words) {
    input.classList.toggle("is-right", right);
    const status = input.closest(".auth-field").querySelector('[role="status"]');
    const text = right ? words : "";
    // Only on a change, so typing on in a right field does not repeat the words.
    if (status.textContent !== text) status.textContent = text;
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
    show(confirmation, same, "兩次密碼相同");
  }

  year.addEventListener("input", checkYear);
  password.addEventListener("input", checkConfirmation);
  confirmation.addEventListener("input", checkConfirmation);
  // A year the server kept after a mistake elsewhere on the form is checked on arrival.
  checkYear();
  checkConfirmation();
})();
