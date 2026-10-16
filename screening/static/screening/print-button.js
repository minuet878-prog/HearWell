// Health report (spec docs/specs/phase8_c3_report.md): the button opens the browser's print
// dialog, where people can print or save as PDF.
document.getElementById("print-button")?.addEventListener("click", () => window.print());
