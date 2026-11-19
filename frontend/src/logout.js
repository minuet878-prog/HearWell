import { clearAllDrafts } from "./draft.js";
import { clearAllGuestResults } from "./guest-results.js";

// Unfinished answers are health data: they leave this device on logout (spec 4.2)
// and on account deletion (spec phase7_account_deletion.md, review 2). So do guest results kept
// here (security check 2026-11-19): the next person signing in would be asked to keep them.
for (const id of ["logout-form", "delete-account-form"]) {
  document.getElementById(id)?.addEventListener("submit", () => {
    clearAllDrafts();
    clearAllGuestResults();
  });
}
