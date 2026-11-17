import { sendCount } from "./guest-count.js";

// Spec #655 (#673): the signed-out home's two doors are plain links; a press of one sends its
// kind to the 訪客月計數 as the page moves on. A search engine reads the page but never presses
// a link, so it never counts. Without JavaScript the doors still go, uncounted (grill).
export function countDoorPresses() {
  for (const door of document.querySelectorAll("[data-door]")) {
    door.addEventListener("click", () => sendCount(door.dataset.door));
  }
}
