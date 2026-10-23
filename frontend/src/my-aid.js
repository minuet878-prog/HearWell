// 我的助聽器與補助 (#287): the level question only matters with 用身障補助, so it is hidden
// otherwise. Without JavaScript it stays in sight, and saving drops a level given with any
// other answer.
const level = document.querySelector("[data-aid-level]");
const subsidy = () => document.querySelector('input[name="subsidy"]:checked')?.value;
const show = () => {
  level.hidden = subsidy() !== "disability";
};

if (level) {
  show();
  level.form.addEventListener("change", (event) => {
    if (event.target.name === "subsidy") show();
  });
}
