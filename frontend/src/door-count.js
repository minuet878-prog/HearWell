// Spec #655 (#673): the signed-out home's two doors are plain links; a press of one sends its
// kind to the 訪客月計數 as the page moves on. A search engine reads the page but never presses
// a link, so it never counts. Without JavaScript the doors still go, uncounted (grill).
export function countDoorPresses(root = document) {
  for (const door of root.querySelectorAll("[data-door]")) {
    door.addEventListener("click", () => {
      // keepalive: still sent though the page is already moving to the door's address.
      window.fetch("/api/guest-counts/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: door.dataset.door }),
        keepalive: true,
      });
    });
  }
}
