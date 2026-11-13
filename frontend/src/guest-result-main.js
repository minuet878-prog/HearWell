import { showGuestResult } from "./guest-results.js";

const root = document.getElementById("guest-result");
if (root) {
  showGuestResult({ root });
  // Back to this page from the browser's cache: read it again, home when it is gone (spec #492).
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) showGuestResult({ root });
  });
}
