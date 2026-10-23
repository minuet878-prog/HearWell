// Health report (spec docs/specs/phase-08/phase8_c3_report.md): the button opens the browser's print
// dialog, where people can print or save as PDF.
document.getElementById("print-button")?.addEventListener("click", () => window.print());

// #314: the report's questionnaire folds open on paper too, and close again as they were.
const reportAnswers = [...document.querySelectorAll(".report-answers, .report-fold")];
let openAnswers = [];
window.addEventListener("beforeprint", () => {
  openAnswers = reportAnswers.filter((details) => details.open);
  reportAnswers.forEach((details) => { details.open = true; });
});
window.addEventListener("afterprint", () => {
  reportAnswers.forEach((details) => { details.open = openAnswers.includes(details); });
});
