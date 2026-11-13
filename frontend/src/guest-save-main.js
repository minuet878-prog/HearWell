import { askToSaveGuestResults, saveGuestResults } from "./guest-results.js";

const root = document.getElementById("guest-save");
// From the save card it saves straight away; the other ways in ask first (#497).
if (root) ("asking" in root.dataset ? askToSaveGuestResults : saveGuestResults)({ root });
