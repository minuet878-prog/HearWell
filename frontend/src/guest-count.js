// Adds one to this month's column of the 訪客月計數 (specs #677, #655): a clinic card's or the
// address 傳給他 sent opened in a browser (arrival-count.js), or a door pressed on the signed-out
// home (door-count.js). keepalive: still sent when the page moves on before it has gone.
export function sendCount(kind) {
  window.fetch("/api/guest-counts/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind }),
    keepalive: true,
  });
}
