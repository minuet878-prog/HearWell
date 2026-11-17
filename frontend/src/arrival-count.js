import { sendCount } from "./guest-count.js";

// Spec #677 (ADR 0066): a clinic card's address lands here with the card's mark. Once the page has
// opened in a browser, send that card's kind to the 訪客月計數 and take the mark off the address,
// so a reload, or the address passed on, counts nothing more. A link preview or a search engine
// fetching the card's address never runs this, so it never counts.
// Spec #655 (#674): the address 傳給他 sends lands on the wizard's age step with send, counted
// the same way.
const MARKS = {
  "clinic-elder": "clinic_elder",
  "clinic-family": "clinic_family",
  send: "send_opened",
};

export function countArrival() {
  const address = new URL(window.location.href);
  const kind = MARKS[address.searchParams.get("via")];
  if (!kind) return;
  sendCount(kind);
  address.searchParams.delete("via");
  window.history.replaceState(window.history.state, "", address);
}
