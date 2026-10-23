// 配戴之後's question on the 選配路線 and its chapter (#287, #295): the level only matters
// with 用身障補助, so it is hidden otherwise. Without JavaScript it stays in sight, and saving
// drops a level given with any other answer.
const level = document.querySelector("[data-aid-level]");
const subsidy = () => document.querySelector('input[name="subsidy"]:checked')?.value;
const show = () => {
  level.hidden = subsidy() !== level.dataset.shownWith;
};

if (level) {
  show();
  level.form.addEventListener("change", (event) => {
    if (event.target.name === "subsidy") show();
  });
}
