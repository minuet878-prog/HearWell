import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { countArrival } from "./arrival-count.js";

// Spec #677 (ADR 0066): a clinic card's landing page, once open in a browser, sends the card's
// kind to the 訪客月計數 once and takes the card's mark off the address, so reloading or passing
// the address on counts nothing more. A link preview never runs this, so it never counts.
const open = (address) => window.history.replaceState(null, "", address);

beforeEach(() => {
  window.fetch = vi.fn(async () => new Response(null, { status: 204 }));
});

afterEach(() => open("/"));

const sent = () => window.fetch.mock.calls.map(([url, init]) => [url, init.method, JSON.parse(init.body)]);

describe("countArrival", () => {
  it("counts the elder card once and takes its mark off the address", () => {
    open("/questionnaire_list?via=clinic-elder");
    countArrival();
    expect(sent()).toEqual([["/api/guest-counts/", "POST", { kind: "clinic_elder" }]]);
    expect(window.location.pathname + window.location.search).toBe("/questionnaire_list");
  });

  it("counts the family card once and takes its mark off the address", () => {
    open("/family?via=clinic-family");
    countArrival();
    expect(sent()).toEqual([["/api/guest-counts/", "POST", { kind: "clinic_family" }]]);
    expect(window.location.pathname + window.location.search).toBe("/family");
  });

  // Spec #655 (#674) acceptance 24: the address 傳給他 sends, opened in a browser.
  it("counts an open of what 傳給他 sent once and takes its mark off the address", () => {
    open("/questionnaire_list?via=send");
    countArrival();
    expect(sent()).toEqual([["/api/guest-counts/", "POST", { kind: "send_opened" }]]);
    expect(window.location.pathname + window.location.search).toBe("/questionnaire_list");
  });

  it("keeps the rest of the address", () => {
    open("/questionnaire_list?wizard=1&via=clinic-elder#top");
    countArrival();
    expect(window.location.search).toBe("?wizard=1");
    expect(window.location.hash).toBe("#top");
  });

  it("sends nothing once the mark is gone, as after a reload", () => {
    open("/questionnaire_list?via=clinic-elder");
    countArrival();
    countArrival();
    expect(window.fetch).toHaveBeenCalledTimes(1);
  });

  it("sends nothing and leaves the address alone without a card's mark", () => {
    for (const address of ["/family", "/questionnaire_list?via=sent", "/family?via=clinic-other"]) {
      open(address);
      countArrival();
      expect(window.location.pathname + window.location.search).toBe(address);
    }
    expect(window.fetch).not.toHaveBeenCalled();
  });

  it("keeps sending even when the page is left at once", () => {
    open("/family?via=clinic-family");
    countArrival();
    expect(window.fetch.mock.calls[0][1].keepalive).toBe(true);
  });
});
