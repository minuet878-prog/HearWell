import { openFoldsForJump, setUpGuideCards } from "./guide.js";

const row = document.querySelector(".guide-cards");
if (row) setUpGuideCards(row);
else openFoldsForJump();
