// Spec #611 N3 (ticket #616; mockup-613-filling.html 三): in a form with several text fields,
// every one but the last tells the phone keyboard to say 下一個, and Enter there (that key, or
// Enter on a computer) moves to the next text field instead of sending a form not yet filled in.
// The last one is left to the phone and sends as before. Set here, not by the server, so without
// JavaScript no key says 下一個 and then sends. Buttons (顯示) and hidden fields are not fields.
(function () {
  const TEXT_TYPES = ["text", "email", "password", "number"];

  document.querySelectorAll("form").forEach((form) => {
    const fields = [...form.elements].filter(
      (element) => element.tagName === "INPUT" && TEXT_TYPES.includes(element.type),
    );
    fields.slice(0, -1).forEach((field, i) => {
      field.setAttribute("enterkeyhint", "next");
      field.addEventListener("keydown", (event) => {
        // The Enter that picks a character in 注音 or another input method only picks it.
        if (event.key !== "Enter" || event.isComposing || event.keyCode === 229) return;
        event.preventDefault();
        fields[i + 1].focus();
      });
    });
  });
})();
