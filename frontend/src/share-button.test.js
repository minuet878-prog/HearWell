import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

// share-button.js, a plain static file (not a Vite entry), run as the page does. Spec #655
// (#674) acceptance 18: 傳給他 sends one text, the message with the address after it, since some
// apps keep only the address when given both; the family page and shared report send an address.
const SCRIPT = resolve(process.cwd(), "../screening/static/screening/share-button.js");

const button = () => document.getElementById("share-button");

function page(attributes) {
  document.body.innerHTML = `<button id="share-button" type="button" ${attributes} hidden>傳</button>`;
  new Function(readFileSync(SCRIPT, "utf-8"))();
}

afterEach(() => {
  delete navigator.share;
  document.body.innerHTML = "";
});

const withShareSheet = () => {
  const share = vi.fn(() => Promise.resolve());
  Object.defineProperty(navigator, "share", { configurable: true, value: share });
  return share;
};

describe("share button", () => {
  it("sends 傳給他's message and address as one text, without a separate address", () => {
    const share = withShareSheet();
    page('data-text="分享你一個聽力自我篩檢。&#10;https://example.com/questionnaire_list?via=send"');
    expect(button().hidden).toBe(false);
    button().click();
    expect(share).toHaveBeenCalledWith({
      text: "分享你一個聽力自我篩檢。\nhttps://example.com/questionnaire_list?via=send",
    });
  });

  it("still sends a title and an address where the page gives those", () => {
    const share = withShareSheet();
    page('data-url="https://example.com/shared/abc" data-title="聽伴聽力報告"');
    button().click();
    expect(share).toHaveBeenCalledWith({ title: "聽伴聽力報告", url: "https://example.com/shared/abc" });
  });

  it("stays hidden without the phone's share sheet", () => {
    page('data-text="x"');
    expect(button().hidden).toBe(true);
  });
});
