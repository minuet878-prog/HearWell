import { saveGuestResults } from "./guest-results.js";

const root = document.getElementById("guest-save");
if (root) saveGuestResults({ root });
