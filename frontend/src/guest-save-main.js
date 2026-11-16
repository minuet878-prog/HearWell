import { askToSaveGuestResults, loadGuestResults, saveGuestResults } from "./guest-results.js";

const root = document.getElementById("guest-save");
// From the save card it saves straight away; the other ways in ask first (#497).
if (root) {
  if ("asking" in root.dataset) askToSaveGuestResults({ root });
  else saveGuestResults({ root, keys: loadGuestResults().map((result) => result.key) });
}
