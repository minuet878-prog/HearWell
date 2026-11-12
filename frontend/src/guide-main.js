// #467: 我的選配指引 and the guide chapters, loaded by their templates. Each part finds nothing to
// do on the pages without it.
import { openFoldsForJump, playRouteOnce, setUpRouteStops } from "./guide.js";

playRouteOnce();
setUpRouteStops();
openFoldsForJump();
