import { startSavePage } from "./guest-results.js";

const root = document.getElementById("guest-save");
// From the save card pressed in this tab it saves straight away; the other ways in ask first
// (#497, Codex cross review of #492).
if (root) startSavePage({ root });
