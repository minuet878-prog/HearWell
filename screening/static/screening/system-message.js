// The feedback batch (F1, the owner's call 2026-11-16): the bar a page opens with after something was
// done gets the focus, as GOV.UK's success banner does, so a screen reader says it; words already
// on the page when it opens are not read out by themselves. The page stays where it is.
document.querySelector(".system-message")?.focus({ preventScroll: true });
