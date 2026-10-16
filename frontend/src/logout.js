import { clearAllDrafts } from "./draft.js";

// Unfinished answers are health data: they leave this device on logout (spec 4.2)
// and on account deletion (spec phase7_account_deletion.md, review 2).
for (const id of ["logout-form", "delete-account-form"]) {
  document.getElementById(id)?.addEventListener("submit", clearAllDrafts);
}
