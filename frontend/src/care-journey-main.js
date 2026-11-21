// #459: the home page's 照顧旅程, loaded by index.html.
import { openOneAtATime, playOnceATab, stampOnce } from "./step-list.js";

playOnceATab(window, "journey-played", "journey-plays");
openOneAtATime(document, ".journey-steps", ".journey-about");
stampOnce(document, ".journey-steps");
