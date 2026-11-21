// #459: the home page's 照顧旅程, loaded by index.html.
import { openOneAtATime, playOnceATab, playOnceOpened } from "./step-list.js";

playOnceATab(window, "journey-played", "journey-plays");
openOneAtATime(document, ".journey-steps", ".journey-about");
playOnceOpened(document, ".journey-steps");
