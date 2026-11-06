// 點選看說明 (#428, spec #426): the server sends every option with its explanation, so without
// JavaScript they all stay on the page. This folds them away; choosing an option writes its
// explanation into the question's live region, so a screen reader says it, and choosing another
// replaces it. Nothing is scored, kept or sent. No animation (ADR 0006, ADR 0028).
(function () {
  document.querySelectorAll("[data-pick-explain]").forEach((question) => {
    const list = question.querySelector("[data-pick-explanations]");
    const live = question.querySelector("[data-pick-live]");
    const explanations = list.children;
    const radios = [...question.querySelectorAll("input[type=radio]")];
    const show = (radio) => {
      // All of the option's item but its first child, the name already beside its radio (#429).
      const [, ...parts] = explanations[radios.indexOf(radio)].children;
      live.replaceChildren(...parts.map((part) => part.cloneNode(true)));
    };
    list.hidden = true;
    radios.forEach((radio) => radio.addEventListener("change", () => show(radio)));
    // autocomplete="off" keeps Chromium, where the tests run, from bringing a choice back too late
    // for this to see; a browser that still brings one back first gets its explanation.
    const chosen = radios.find((radio) => radio.checked);
    if (chosen) show(chosen);
  });
})();
