import { clearAllDrafts } from "./draft.js";

// Unfinished answers are health data: they leave this device on logout (spec 4.2).
document.getElementById("logout-form")?.addEventListener("submit", clearAllDrafts);
