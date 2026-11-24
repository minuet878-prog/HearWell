// Health report (spec docs/specs/phase-08/phase8_c3_report.md): the button opens the browser's print
// dialog, where people can print or save as PDF.
document.getElementById("print-button")?.addEventListener("click", () => window.print());

// C5: toggle all top-level .report-fold details on screen (leaving nested .report-answers as they are).
const reportFolds = [...document.querySelectorAll(".report-fold")];
const foldToggle = document.getElementById("report-fold-toggle");
if (foldToggle && reportFolds.length > 0) {
  const syncToggle = () => {
    const allOpen = reportFolds.every((fold) => fold.open);
    foldToggle.textContent = allOpen ? "全部收合" : "全部展開";
    foldToggle.setAttribute("aria-expanded", String(allOpen));
  };
  foldToggle.hidden = false;
  syncToggle();
  foldToggle.addEventListener("click", () => {
    const nextOpen = !reportFolds.every((fold) => fold.open);
    reportFolds.forEach((fold) => { fold.open = nextOpen; });
    syncToggle();
  });
  reportFolds.forEach((fold) => fold.addEventListener("toggle", syncToggle));
}

// #314: the report's questionnaire folds open on paper too, and close again as they were. #469:
// so do the family zone's folded sources (陪診清單, 補助檢核, 期限試算).
const reportDetails = [
  ...document.querySelectorAll(".report-answers, .report-fold, .family-sources"),
];
let openAnswers = [];
window.addEventListener("beforeprint", () => {
  openAnswers = reportDetails.filter((details) => details.open);
  reportDetails.forEach((details) => { details.open = true; });
});
window.addEventListener("afterprint", () => {
  reportDetails.forEach((details) => { details.open = openAnswers.includes(details); });
});
