import { askAboutGuestResults } from "./guest-results.js";

// #497: layout.html loads this on every page someone signed in opens, but the save page itself.
const script = document.querySelector("script[data-ask-url]");
if (script) askAboutGuestResults({ askUrl: script.dataset.askUrl });
