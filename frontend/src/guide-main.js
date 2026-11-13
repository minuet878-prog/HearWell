// #467: 我的選配指引 and the guide chapters, loaded by their templates. Each part finds nothing to
// do on the pages without it.
import { openFoldsForJump, playRouteOnce } from "./guide.js";
import { tickInPlace } from "./journey-todos.js";
import { openOneAtATime } from "./step-list.js";

playRouteOnce();
openOneAtATime(document, ".route", ".route-about");
openFoldsForJump();
tickInPlace(); // #481: the 您在這裡 stop's 手動待辦
