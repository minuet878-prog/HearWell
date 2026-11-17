// Spec #677 (ADR 0066): a clinic card's address lands here with the card's mark. Once the page has
// opened in a browser, send that card's kind to the 訪客月計數 and take the mark off the address,
// so a reload, or the address passed on, counts nothing more. A link preview or a search engine
// fetching the card's address never runs this, so it never counts.
const MARKS = { "clinic-elder": "clinic_elder", "clinic-family": "clinic_family" };

export function countArrival() {
  const address = new URL(window.location.href);
  const kind = MARKS[address.searchParams.get("via")];
  if (!kind) return;
  // keepalive: still sent when the reader moves on before it has gone.
  window.fetch("/api/guest-counts/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind }),
    keepalive: true,
  });
  address.searchParams.delete("via");
  window.history.replaceState(window.history.state, "", address);
}
