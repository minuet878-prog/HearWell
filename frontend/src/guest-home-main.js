import { showGuestHome } from "./guest-home.js";

const root = document.getElementById("guest-home");
const data = document.getElementById("guest-home-data");
if (root && data) {
  const questionnaires = JSON.parse(data.textContent);
  showGuestHome({ root, questionnaires });
  // Back from the browser's cache after saving or clearing: what is kept now.
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) showGuestHome({ root, questionnaires });
  });
}
