import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

// Spec #426 acceptance 6-8, ticket #428: 點選看說明. A plain static file (not a Vite entry), so the
// test runs it as the page does, on what screening/family/pick_explain.html sends.
const SCRIPT = resolve(process.cwd(), "../screening/static/screening/pick-explain.js");

function question(code, prompt, options) {
  return `
    <fieldset data-pick-explain>
      <legend>${prompt}</legend>
      <div class="choice-group choice-stack">
        ${options.map(([label]) => `<label><input type="radio" name="${code}"><span>${label}</span></label>`).join("")}
      </div>
      <ul data-pick-explanations>
        ${options.map(([label, words]) => `<li><strong>${label}</strong><p class="mb-0">${words}</p></li>`).join("")}
      </ul>
      <div aria-live="polite" data-pick-live></div>
    </fieldset>`;
}

const serverPage = () => {
  document.body.innerHTML =
    question("tv-on", "他在看電視", [
      ["提高音量", "可以試試先關小聲"],
      ["關小聲再說", "這樣有幫助"],
    ]) +
    question("other-room", "您在廚房", [
      ["大聲叫他", "可以試試走過去"],
      ["走到他面前", "他看得到您的臉"],
    ]);
};

const runScript = () => new Function(readFileSync(SCRIPT, "utf-8"))();

const group = (i) => document.querySelectorAll("[data-pick-explain]")[i];
const radio = (i, option) => group(i).querySelectorAll("input")[option];
const live = (i) => group(i).querySelector('[aria-live="polite"]');

// What can be read: anything not inside something hidden.
const showing = (i) =>
  [...group(i).querySelectorAll("p")]
    .filter((words) => !words.closest("[hidden]"))
    .map((words) => words.textContent);

describe("pick to explain", () => {
  beforeEach(serverPage);

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("shows every explanation when the script has not run", () => {
    expect(showing(0)).toEqual(["可以試試先關小聲", "這樣有幫助"]);
    expect(showing(1)).toEqual(["可以試試走過去", "他看得到您的臉"]);
  });

  it("folds the explanations away once it runs, with nothing chosen", () => {
    runScript();
    expect(showing(0)).toEqual([]);
    expect(showing(1)).toEqual([]);
    expect(live(0).textContent).toBe("");
  });

  it("shows only the chosen option's explanation, in the live region", () => {
    runScript();
    radio(0, 1).click();
    expect(showing(0)).toEqual(["這樣有幫助"]);
    expect(live(0).textContent).toBe("這樣有幫助");
  });

  it("swaps the explanation when the choice changes", () => {
    runScript();
    radio(0, 1).click();
    radio(0, 0).click();
    expect(showing(0)).toEqual(["可以試試先關小聲"]);
    expect(live(0).textContent).toBe("可以試試先關小聲");
  });

  it("keeps each question to itself", () => {
    runScript();
    radio(0, 0).click();
    radio(1, 1).click();
    expect(showing(0)).toEqual(["可以試試先關小聲"]);
    expect(showing(1)).toEqual(["他看得到您的臉"]);
  });

  // A reload or 上一頁 can bring a choice back: it must not sit there with no explanation.
  it("shows the explanation of a choice the browser brought back", () => {
    radio(1, 0).checked = true;
    runScript();
    expect(showing(1)).toEqual(["可以試試走過去"]);
    expect(showing(0)).toEqual([]);
  });

  // #429: an option can carry more than a paragraph. All of it moves, links still working; the
  // option's own name, already beside its radio, does not come along.
  it("shows all of a longer explanation, with its lists and links", () => {
    group(0).querySelector("li").insertAdjacentHTML(
      "beforeend",
      '<h3>可以試的說法</h3><ul><li>「我陪您去」</li></ul><a href="/guide">看選配指引</a>',
    );
    runScript();
    radio(0, 0).click();
    expect(live(0).querySelector("h3").textContent).toBe("可以試的說法");
    expect(live(0).querySelector("ul li").textContent).toBe("「我陪您去」");
    expect(live(0).querySelector("a").getAttribute("href")).toBe("/guide");
    expect(live(0).querySelector("strong")).toBeNull();
    expect(showing(0)).toEqual(["可以試試先關小聲"]);

    radio(0, 1).click();
    expect(live(0).textContent).toBe("這樣有幫助");
  });

  // #435: an option's steps carry boxes to tick and hidden drawings. They move as they are, the
  // copies tick, and a tick does not outlive the choice: the copy goes, what is folded stays empty.
  describe("with boxes to tick", () => {
    const shown = () => live(0).querySelector("input[type=checkbox]");
    const folded = () => group(0).querySelector("[data-pick-explanations] input[type=checkbox]");

    beforeEach(() => {
      group(0).querySelector("li").insertAdjacentHTML(
        "beforeend",
        '<ol><li><svg aria-hidden="true" focusable="false"></svg>' +
          '<label><input type="checkbox" autocomplete="off"><span>擦乾淨</span></label></li></ol>',
      );
      runScript();
    });

    it("copies them with their drawings, and ticking one leaves what is folded alone", () => {
      radio(0, 0).click();
      expect(live(0).querySelector("svg").getAttribute("aria-hidden")).toBe("true");
      live(0).querySelector("label").click();
      expect(shown().checked).toBe(true);
      expect(folded().checked).toBe(false);
    });

    it("starts them empty again after another choice", () => {
      radio(0, 0).click();
      shown().click();
      radio(0, 1).click();
      expect(shown()).toBeNull();
      radio(0, 0).click();
      expect(shown().checked).toBe(false);
    });

    it("keeps what is folded out of reach, inside a hidden list", () => {
      expect(folded().closest("[hidden]")).not.toBeNull();
    });
  });

  it("keeps nothing and sends nothing", () => {
    runScript();
    radio(0, 1).click();
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    expect(readFileSync(SCRIPT, "utf-8")).not.toMatch(/localStorage|sessionStorage|fetch|XMLHttp/);
  });
});
