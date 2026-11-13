// #459: the home page's 照顧旅程, loaded by index.html.
import { tickInPlace } from "./journey-todos.js";
import { openOneAtATime, playOnceATab } from "./step-list.js";

playOnceATab(window, "journey-played", "journey-plays");
openOneAtATime(document, ".journey-steps", ".journey-about");
tickInPlace(); // #481: the 現在這一步's 手動待辦
