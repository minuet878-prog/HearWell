import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AudiogramApp from "./AudiogramApp.jsx";
import { CHART, x, y } from "./audiogram.js";

const TODAY = "2026-10-16";
let navigate;

// jsdom has no layout: make one screen pixel equal one chart unit, and scrolling a no-op.
// Nor media queries: motion is not reduced unless a test says so (#618's 看示範).
let reduceMotion;
beforeEach(() => {
  navigate = vi.fn();
  reduceMotion = false;
  window.matchMedia = (query) => ({ matches: query === "(prefers-reduced-motion: reduce)" && reduceMotion });
  Element.prototype.scrollIntoView = vi.fn();
  SVGElement.prototype.getBoundingClientRect = () => ({
    left: 0,
    top: 0,
    width: CHART.width,
    height: CHART.height,
  });
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({ id: 42 }) }),
  );
});
afterEach(() => {
  vi.useRealTimers();
  cleanup();
});

// #199, #200: four steps (date, right ear, left ear, confirm) on one screen.
const forward = () => fireEvent.click(screen.getByRole("button", { name: /^下一步：標右耳$|^右耳標完了，換左耳$|^左耳標完了，確認存檔$/ }));
const back = () => fireEvent.click(screen.getByRole("button", { name: "上一步" }));
const renderApp = () => render(<AudiogramApp today={TODAY} csrfToken="csrf-token" navigate={navigate} />);
// Most tests mark points: open on the right ear's step, or the left ear's.
const renderRight = () => {
  renderApp();
  forward();
};
const renderLeft = () => {
  renderRight();
  forward();
};
const progress = () => document.querySelector(".step-progress-text").textContent;
// From any ear step on to the confirm step, then save there.
const confirmAndSave = () => {
  while (!screen.queryByRole("button", { name: "存檔" })) forward();
  save();
};
const chart = () => screen.getByRole("img", { name: /聽力圖/ });
const at = (frequency, db) => ({ clientX: x(frequency), clientY: y(db), pointerId: 1, pointerType: "mouse" });
const press = (frequency, db) => fireEvent.pointerDown(chart(), at(frequency, db));
const move = (frequency, db) => fireEvent.pointerMove(chart(), at(frequency, db));
const release = (frequency, db) => fireEvent.pointerUp(chart(), at(frequency, db));
const drag = (frequency, from, to) => {
  press(frequency, from);
  move(frequency, to);
  release(frequency, to);
};
const pickSymbol = (name) => fireEvent.click(screen.getByRole("button", { name: new RegExp(name) }));
const point = (key) => chart().querySelector(`[data-point="${key}"]`);
const magnifier = () => document.querySelector(".audiogram-magnifier");
const select = (name) => screen.getByRole("combobox", { name });
// The 2026-11-14 walkthrough (mockup 12A): the date is typed as on a report, 民國 year, month, day.
const dateGroup = () => screen.queryByRole("group", { name: "檢查日期" });
const typeDate = (year, month, day) => {
  fireEvent.change(screen.getByLabelText("民國年"), { target: { value: year } });
  fireEvent.change(screen.getByLabelText("月"), { target: { value: month } });
  fireEvent.change(screen.getByLabelText("日"), { target: { value: day } });
};
const setDate = (iso) => {
  const [year, month, day] = iso.split("-").map(Number);
  typeDate(String(year - 1911), String(month), String(day));
};
const save = () => fireEvent.click(screen.getByRole("button", { name: "存檔" }));
// #333 (D4): a switch named 遮蔽, with 開 or 關 written beside it.
const maskToggle = () => screen.getByRole("switch", { name: "遮蔽" });
const framed = () => chart().closest(".audiogram-chart").classList.contains("masking");
const maskBox = (name) => screen.getByRole("checkbox", { name: `${name} 遮蔽` });

describe("input", () => {
  it("starts empty with right-ear air selected (acceptance 1)", () => {
    renderApp();
    expect(dateGroup()).toBeTruthy();
    forward();
    expect(chart().querySelectorAll("[data-point]")).toHaveLength(0);
    expect(screen.getByRole("button", { name: /右耳氣導/ }).getAttribute("aria-pressed")).toBe("true");
    expect(maskToggle().getAttribute("aria-checked")).toBe("false");
    expect(maskToggle().textContent).toBe("遮蔽關");
    expect(framed()).toBe(false);
    expect(screen.getByRole("button", { name: /清除/ }).disabled).toBe(true);
  });

  it("drags a point into place with a magnifier (acceptance 2)", () => {
    renderRight();
    press(1000, 30);
    move(1000, 42);
    expect(magnifier().textContent).toBe("1000 Hz 40 dB");
    release(1000, 42);
    const marked = point("right-air-1000");
    expect(marked.dataset.db).toBe("40");
    expect(marked.querySelector("circle").getAttribute("stroke")).toBe("#c0392b");
    expect(magnifier()).toBeNull();
  });

  it("the magnifier moves beside the point when there is no room above (review 1-1)", () => {
    renderRight();
    press(1000, 40);
    expect(magnifier().dataset.place).toBe("above");
    move(1000, -10);
    expect(magnifier().dataset.place).toBe("beside");
    release(1000, -10);
  });

  it("keeps the frequency chosen on press (acceptance 3)", () => {
    renderRight();
    press(1000, 40);
    release(2000, 40);
    expect(point("right-air-1000")).not.toBeNull();
    expect(point("right-air-2000")).toBeNull();
  });

  it("moves an existing point (acceptance 4)", () => {
    renderRight();
    drag(1000, 40, 40);
    drag(1000, 40, 60);
    expect(chart().querySelectorAll("[data-point]")).toHaveLength(1);
    expect(point("right-air-1000").dataset.db).toBe("60");
  });

  it("tapping a point deletes it (acceptance 5)", () => {
    renderRight();
    drag(2000, 40, 40);
    drag(1000, 40, 40);
    press(1000, 40);
    release(1000, 40);
    expect(point("right-air-1000")).toBeNull();
    expect(point("right-air-2000")).not.toBeNull();
  });

  it("clears the last marked point (acceptance 6)", () => {
    renderRight();
    drag(500, 30, 30);
    drag(1000, 40, 40);
    const clear = screen.getByRole("button", { name: "清除 右耳氣導 1000 Hz" });
    fireEvent.click(clear);
    expect(point("right-air-1000")).toBeNull();
    expect(point("right-air-500")).not.toBeNull();
    expect(screen.getByRole("button", { name: /清除/ }).disabled).toBe(true);
  });

  it("air past the bottom is no response, not joined by the line (acceptance 7)", () => {
    renderRight();
    const lines = () => [...chart().querySelectorAll(".air-line-right")].map((l) => l.getAttribute("points"));
    drag(500, 100, 100);
    drag(1000, 110, 110);
    drag(2000, 110, 110);
    drag(4000, 110, 110);
    expect(lines()).toEqual([[500, 1000, 2000, 4000].map((f) => `${x(f)},${y(f === 500 ? 100 : 110)}`).join(" ")]);
    drag(1000, 110, 135);
    const nr = point("right-air-1000");
    expect(nr.dataset.db).toBe("120");
    expect(nr.dataset.noResponse).toBe("true");
    expect(nr.querySelector(".no-response-arrow")).not.toBeNull();
    // 500 is left alone; 2000-4000 stay joined; nothing runs through 1000.
    expect(lines()).toEqual([`${x(2000)},${y(110)} ${x(4000)},${y(110)}`]);
    drag(6000, 10, -40);
    expect(point("right-air-6000").dataset.db).toBe("-10");
  });

  it("bone snaps to its own frequencies (acceptance 8)", () => {
    renderLeft();
    pickSymbol("左耳骨導");
    drag(3000, 40, 40);
    expect(point("left-bone-3000")).toBeNull();
    expect(point("left-bone-4000")).not.toBeNull();
    drag(8000, 50, 50);
    expect(point("left-bone-8000")).toBeNull();
    expect(point("left-bone-4000").dataset.db).toBe("50");
    drag(6000, 60, 60);
    expect(point("left-bone-6000")).toBeNull();
    expect(point("left-bone-4000").dataset.db).toBe("60");
    drag(250, 20, 20);
    expect(point("left-bone-500")).not.toBeNull();
  });

  it("bone past 80 is no response at 80 (acceptance 9)", () => {
    renderLeft();
    pickSymbol("左耳骨導");
    press(1000, 60);
    move(1000, 95);
    expect(magnifier().textContent).toBe("1000 Hz 無反應");
    release(1000, 95);
    const nr = point("left-bone-1000");
    expect(nr.dataset.db).toBe("80");
    expect(nr.dataset.noResponse).toBe("true");
    expect(nr.querySelector("text").textContent).toBe(">");
    expect(nr.querySelector("text").getAttribute("fill")).toBe("#1f4e8c");
    expect(nr.querySelector(".no-response-arrow")).not.toBeNull();
  });

  it("the value table and the chart stay in sync (acceptance 10)", () => {
    renderRight();
    fireEvent.change(select("右耳氣導 1000 Hz"), { target: { value: "40" } });
    fireEvent.change(select("右耳氣導 2000 Hz"), { target: { value: "nr" } });
    expect(point("right-air-1000").dataset.db).toBe("40");
    expect(point("right-air-2000").dataset.noResponse).toBe("true");
    drag(1000, 40, 55);
    expect(select("右耳氣導 1000 Hz").value).toBe("55");
    fireEvent.change(select("右耳氣導 1000 Hz"), { target: { value: "" } });
    expect(point("right-air-1000")).toBeNull();
    // Bone only offers 500, 1000, 2000, 4000 and stops at 80.
    expect(screen.queryByRole("combobox", { name: "右耳骨導 3000 Hz" })).toBeNull();
    const bone = [...select("右耳骨導 1000 Hz").options].map((o) => o.value);
    expect(bone).toContain("80");
    expect(bone).not.toContain("85");
  });

  it("ends the drag when the browser drops pointer capture before the release", () => {
    // Seen in Chrome with a Mac trackpad: lostpointercapture first, then pointerup on another element.
    renderRight();
    press(1000, 100);
    move(1000, 135);
    fireEvent.lostPointerCapture(chart(), { pointerId: 1 });
    fireEvent.pointerUp(screen.getByText("選下面的符號"), at(1000, 135));
    expect(point("right-air-1000").dataset.noResponse).toBe("true");
    expect(magnifier()).toBeNull();
    // The drag is over: moving no longer drags, and a stray release on the chart changes nothing.
    move(1000, 40);
    expect(magnifier()).toBeNull();
    release(1000, 135);
    expect(point("right-air-1000").dataset.db).toBe("120");
  });

  it("pressing does not select text or start the browser's own drag", () => {
    renderRight();
    const event = new Event("pointerdown", { bubbles: true, cancelable: true });
    Object.assign(event, at(1000, 40));
    chart().dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });
});

// A finger marks the moment it lands, as a mouse does; the 0.3 s rest of #353 left a tap doing
// nothing once the marking page no longer scrolled much.
describe("touch", () => {
  const finger = (frequency, db) => ({ ...at(frequency, db), pointerType: "touch" });
  const touchDown = (...args) => fireEvent.pointerDown(chart(), finger(...args));
  const touchMove = (...args) => fireEvent.pointerMove(chart(), finger(...args));
  const touchUp = (...args) => fireEvent.pointerUp(chart(), finger(...args));
  // fireEvent returns false when a listener called preventDefault, i.e. the page did not scroll.
  const scrolls = () => fireEvent.touchMove(chart());

  it("a finger marks as it lands, and dragging does not scroll the page", () => {
    renderRight();
    expect(chart().style.touchAction).toBe("pinch-zoom");
    expect(chart().getAttribute("aria-label")).toBe("聽力圖（用手指按住拖曳標記；鍵盤請用下方的數值表）");
    touchDown(1000, 40);
    expect(magnifier().textContent).toBe("1000 Hz 40 dB");
    expect(scrolls()).toBe(false);
    touchMove(1000, 60);
    touchUp(1000, 60);
    expect(point("right-air-1000").dataset.db).toBe("60");
    expect(magnifier()).toBeNull();
  });

  it("a tap marks, and a tap on the point deletes it", () => {
    renderRight();
    touchDown(1000, 40);
    touchUp(1000, 40);
    expect(point("right-air-1000").dataset.db).toBe("40");
    touchDown(1000, 40);
    touchUp(1000, 40);
    expect(point("right-air-1000")).toBeNull();
  });

  // Pinching the chart still zooms it.
  it("a second finger (zooming) cancels the mark", () => {
    renderRight();
    touchDown(1000, 40);
    fireEvent.pointerDown(chart(), { ...finger(2000, 50), pointerId: 2 });
    expect(magnifier()).toBeNull();
    expect(scrolls()).toBe(true);
    touchUp(1000, 40);
    expect(point("right-air-1000")).toBeNull();
    expect(point("right-air-2000")).toBeNull();
  });

  it("marks nothing when the browser takes the touch", () => {
    renderRight();
    touchDown(1000, 40);
    fireEvent.pointerCancel(chart(), finger(1000, 40));
    expect(magnifier()).toBeNull();
    expect(point("right-air-1000")).toBeNull();
  });
});

describe("masking", () => {
  it("the switch changes the marks and marks new points masked (acceptance 34)", () => {
    renderRight();
    fireEvent.click(maskToggle());
    expect(maskToggle().getAttribute("aria-checked")).toBe("true");
    expect(maskToggle().textContent).toBe("遮蔽開");
    expect(framed()).toBe(true);
    for (const [name, mark] of [["右耳氣導", "△"], ["右耳骨導", "["]]) {
      expect(screen.getByRole("button", { name: new RegExp(name) }).textContent).toContain(mark);
    }
    press(1000, 50);
    expect(magnifier().textContent).toBe("1000 Hz 50 dB 遮蔽");
    release(1000, 50);
    const marked = point("right-air-1000");
    expect(marked.dataset.masked).toBe("true");
    expect(marked.querySelector("polygon").getAttribute("stroke")).toBe("#c0392b");
    fireEvent.click(maskToggle());
    expect(maskToggle().getAttribute("aria-checked")).toBe("false");
    expect(maskToggle().textContent).toBe("遮蔽關");
    expect(framed()).toBe(false);
    press(2000, 50);
    expect(magnifier().textContent).toBe("2000 Hz 50 dB");
    release(2000, 50);
  });

  it("tapping with the other masking converts, the next tap deletes (acceptance 35)", () => {
    renderRight();
    drag(1000, 50, 50);
    fireEvent.click(maskToggle());
    drag(1000, 50, 50);
    expect(point("right-air-1000").dataset.masked).toBe("true");
    drag(1000, 50, 50);
    expect(point("right-air-1000")).toBeNull();
  });

  it("masked and no response together (acceptance 36)", () => {
    renderLeft();
    fireEvent.click(maskToggle());
    pickSymbol("左耳骨導");
    drag(1000, 60, 95);
    const nr = point("left-bone-1000");
    expect(nr.dataset.masked).toBe("true");
    expect(nr.dataset.noResponse).toBe("true");
    expect(nr.querySelector("text").textContent).toBe("]");
    expect(nr.querySelector(".no-response-arrow")).not.toBeNull();
  });

  it("masked air points stay on the line (acceptance 37)", () => {
    renderRight();
    drag(500, 30, 30);
    fireEvent.click(maskToggle());
    drag(1000, 40, 40);
    fireEvent.click(maskToggle());
    drag(2000, 50, 50);
    const lines = [...chart().querySelectorAll(".air-line-right")].map((l) => l.getAttribute("points"));
    expect(lines).toEqual([`${x(500)},${y(30)} ${x(1000)},${y(40)} ${x(2000)},${y(50)}`]);
  });

  it("the table's masking box and the chart stay in sync (acceptance 38)", () => {
    renderRight();
    expect(maskBox("右耳氣導 1000 Hz").disabled).toBe(true);
    fireEvent.change(select("右耳氣導 1000 Hz"), { target: { value: "40" } });
    fireEvent.click(maskBox("右耳氣導 1000 Hz"));
    expect(point("right-air-1000").dataset.masked).toBe("true");
    fireEvent.click(maskBox("右耳氣導 1000 Hz"));
    expect(point("right-air-1000").dataset.masked).toBe("false");
    fireEvent.click(maskToggle());
    drag(2000, 50, 50);
    expect(maskBox("右耳氣導 2000 Hz").checked).toBe(true);
  });

  it("sends masked with every point", async () => {
    renderApp();
    setDate(TODAY);
    forward();
    fireEvent.click(maskToggle());
    drag(1000, 40, 40);
    confirmAndSave();
    await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(JSON.parse(fetch.mock.calls[0][1].body).points).toEqual([
      { ear: "right", conduction: "air", frequency: 1000, db: 40, no_response: false, masked: true },
    ]);
  });

  it("turns off when the next step opens, so the left ear starts unmasked", () => {
    renderRight();
    fireEvent.click(maskToggle());
    forward();
    expect(maskToggle().getAttribute("aria-checked")).toBe("false");
    expect(framed()).toBe(false);
    fireEvent.click(maskToggle());
    back();
    expect(maskToggle().getAttribute("aria-checked")).toBe("false");

    // And when the confirm step sends the user back to change an ear.
    fireEvent.click(maskToggle());
    forward();
    forward();
    Element.prototype.scrollIntoView.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "改右耳" }));
    expect(maskToggle().getAttribute("aria-checked")).toBe("false");
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith({ block: "start" });
  });

  it("says under the switch which of this ear's marks need it, and what it is", () => {
    renderRight();
    const guide = () => maskToggle().nextElementSibling;
    expect(guide().querySelector("p").textContent).toBe("報告上是這些符號，就打開遮蔽再標：");
    const rows = () => [...guide().querySelectorAll("tr")].map((tr) => [...tr.children].map((cell) => cell.textContent));
    expect(rows()).toEqual([
      ["", "沒遮蔽", "有遮蔽"],
      ["氣導", "○", "△"],
      ["骨導", "<", "["],
    ]);
    expect(guide().textContent).toContain("遮蔽是檢查時在另一耳放雜音，不讓另一耳幫忙聽，結果比較準。");
    forward();
    expect(rows().slice(1)).toEqual([
      ["氣導", "✕", "□"],
      ["骨導", ">", "]"],
    ]);
  });
});

// #199, #200 (spec #183 stories 80-93): one thing per step, checked only at the end.
describe("steps", () => {
  it("each step shows only what it needs (#199 acceptance 1)", () => {
    renderApp();
    expect(progress()).toBe("第 1 步／共 4 步：檢查日期");
    expect(dateGroup()).toBeTruthy();
    expect(screen.queryByRole("img", { name: /聽力圖/ })).toBeNull();
    expect(document.querySelectorAll(".step-progress-segment")).toHaveLength(4);
    expect(document.querySelectorAll(".step-progress-segment.is-done")).toHaveLength(1);

    forward();
    expect(progress()).toBe("第 2 步／共 4 步：標右耳");
    expect(screen.getByText("報告上的 O 是右耳（通常是紅色），X 是左耳（通常是藍色）")).toBeTruthy();
    expect([...document.querySelectorAll(".audiogram-howto .step-list-body")].map((li) => li.textContent)).toEqual([
      "選下面的符號",
      "在圖上按住，上下拖到報告上的位置",
      "放開就標好了；標錯就在那個點上點一下，可以刪除",
    ]);
    expect(screen.getByText("報告上符號下面有箭頭（無反應），就往下拖出圖外。")).toBeTruthy();
    const symbols = () => [...document.querySelectorAll(".audiogram-symbol")].map((b) => b.textContent.replace(/ .*/, ""));
    expect(symbols()).toEqual(["右耳氣導", "右耳骨導"]);
    expect(dateGroup()).toBeNull();
    expect(screen.queryByRole("combobox", { name: "左耳氣導 1000 Hz" })).toBeNull();
    expect(maskToggle()).toBeTruthy();
    expect(screen.getByRole("button", { name: /清除/ })).toBeTruthy();

    forward();
    expect(progress()).toBe("第 3 步／共 4 步：標左耳");
    expect(symbols()).toEqual(["左耳氣導", "左耳骨導"]);
    expect(screen.getByRole("button", { name: /左耳氣導/ }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("combobox", { name: "左耳氣導 1000 Hz" })).toBeTruthy();
    expect(screen.queryByRole("combobox", { name: "右耳氣導 1000 Hz" })).toBeNull();

    forward();
    expect(progress()).toBe("第 4 步／共 4 步：確認存檔");
    back();
    expect(progress()).toBe("第 3 步／共 4 步：標左耳");
  });

  it("counts each ear's marks without a total (#199)", () => {
    renderRight();
    const count = () => document.querySelector(".audiogram-count").textContent;
    expect(count()).toBe("右耳已標：氣導 0 個、骨導 0 個");
    drag(1000, 40, 40);
    drag(2000, 50, 50);
    pickSymbol("右耳骨導");
    drag(1000, 30, 30);
    expect(count()).toBe("右耳已標：氣導 2 個、骨導 1 個");
    forward();
    expect(count()).toBe("左耳已標：氣導 0 個、骨導 0 個");
  });

  it("moves on without marking anything (#199 acceptance 2)", () => {
    renderRight();
    forward();
    expect(progress()).toBe("第 3 步／共 4 步：標左耳");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("moves focus to the step it opens, not on first load", () => {
    renderApp();
    const text = document.querySelector(".step-progress-text");
    expect(document.activeElement).not.toBe(text);
    forward();
    expect(document.activeElement).toBe(document.querySelector(".step-progress-text"));
  });

  // An iPhone does not move focus to a tapped button, so the step text keeps focus from the last
  // step and focusing it again scrolls nothing; the page stayed down at the 換左耳 button.
  it("brings the step it opens to the top even when its text already has focus", () => {
    renderRight();
    expect(document.activeElement).toBe(document.querySelector(".step-progress-text"));
    Element.prototype.scrollIntoView.mockClear();
    forward();
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith({ block: "start" });
    expect(Element.prototype.scrollIntoView.mock.contexts[0]).toBe(document.querySelector(".step-progress-text"));
  });

  it("the confirm step shows the date, both ears and how many marks, no reading (#200)", () => {
    renderApp();
    setDate("2026-10-01");
    forward();
    forward();
    pickSymbol("左耳骨導");
    drag(1000, 40, 40);
    forward();
    const main = document.querySelector(".audiogram-app");
    expect(main.textContent).toContain("檢查日期：2026/10/01");
    expect(screen.getByText("右耳：還沒有標任何點")).toBeTruthy();
    expect(screen.getByText("左耳：氣導 0 個、骨導 1 個")).toBeTruthy();
    // One read-only chart with both ears; no symbol to mark with.
    expect(chart()).toBeTruthy();
    expect(document.querySelectorAll(".audiogram-symbol")).toHaveLength(0);
    expect(point("left-bone-1000")).not.toBeNull();
    // The value table is folded; nothing reads the marks before saving.
    expect(document.querySelector("details.audiogram-table").open).toBe(false);
    for (const reading of ["正常", "輕度", "中度", "重度", "四頻平均", "dB HL"]) {
      expect(main.textContent).not.toContain(reading);
    }
  });

  it("jumps back to the step to change (#200 acceptance 1)", () => {
    renderApp();
    forward();
    forward();
    forward();
    expect(screen.getByText("右耳：還沒有標任何點")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "改右耳" }));
    expect(progress()).toBe("第 2 步／共 4 步：標右耳");
    drag(1000, 40, 40);
    forward();
    forward();
    expect(screen.getByText("右耳：氣導 1 個、骨導 0 個")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "改左耳" }));
    expect(progress()).toBe("第 3 步／共 4 步：標左耳");
    forward();
    fireEvent.click(screen.getByRole("button", { name: "改日期" }));
    expect(progress()).toBe("第 1 步／共 4 步：檢查日期");
  });
});

describe("save", () => {
  const sent = () => JSON.parse(fetch.mock.calls[0][1].body);

  // http on a LAN address, or Safari before iOS 15.4: no crypto.randomUUID, which used to throw
  // as the page opened.
  it("opens and saves without crypto.randomUUID", async () => {
    const { getRandomValues } = globalThis.crypto;
    vi.stubGlobal("crypto", { getRandomValues: getRandomValues.bind(globalThis.crypto) });
    try {
      renderApp();
      setDate("2026-10-01");
      forward();
      drag(1000, 40, 40);
      confirmAndSave();
      await waitFor(() => expect(navigate).toHaveBeenCalledWith("/audiograms/42"));
      expect(fetch.mock.calls[0][1].headers["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("posts the points and date, then opens the saved audiogram (acceptance 12)", async () => {
    renderApp();
    setDate("2026-10-01");
    forward();
    drag(1000, 40, 40);
    forward();
    pickSymbol("左耳骨導");
    drag(1000, 60, 95);
    confirmAndSave();
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/audiograms/42"));
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("/api/audiograms/");
    expect(options.headers["X-CSRFToken"]).toBe("csrf-token");
    expect(options.headers["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
    // The same shape as before the steps (#199 acceptance 3).
    expect(sent()).toEqual({
      tested_on: "2026-10-01",
      points: [
        { ear: "right", conduction: "air", frequency: 1000, db: 40, no_response: false, masked: false },
        { ear: "left", conduction: "bone", frequency: 1000, db: 80, no_response: true, masked: false },
      ],
    });
  });

  // #330 (spec #326 B1, acceptance 6): the moment it is saved, before the saved audiogram opens.
  it("shows ✓ 已存檔, says 已存檔, and opens the audiogram 0.6 seconds later", async () => {
    renderApp();
    setDate(TODAY);
    forward();
    drag(1000, 40, 40);
    vi.useFakeTimers();
    confirmAndSave();
    await act(() => vi.advanceTimersByTimeAsync(0));
    const saved = screen.getByRole("button", { name: "已存檔" });
    expect(saved.disabled).toBe(true);
    expect(saved.querySelector("svg").getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByText("已存檔", { selector: "[role=status]" })).toBeTruthy();
    await act(() => vi.advanceTimersByTimeAsync(599));
    expect(navigate).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(1));
    expect(navigate).toHaveBeenCalledWith("/audiograms/42");
  });

  // #330 (spec #326 B1, acceptance 7): a failure keeps today's messages and is never green.
  it.each([
    ["a network failure", () => Promise.reject(new Error("offline")), "存檔失敗"],
    ["500", () => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) }), "存檔失敗"],
    ["403 (login expired)", () => Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({}) }), "登入已經過期"],
    ["409 (already saved)", () => Promise.resolve({ ok: false, status: 409, json: () => Promise.resolve({}) }), "已經存過了"],
  ])("does not say 已存檔 after %s", async (_, reply, message) => {
    fetch.mockImplementationOnce(reply);
    renderApp();
    setDate(TODAY);
    forward();
    drag(1000, 40, 40);
    confirmAndSave();
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain(message));
    expect(screen.queryByText("已存檔")).toBeNull();
    expect(screen.getByRole("button", { name: "存檔" }).disabled).toBe(false);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("types the date in 民國 years and sends it in the western calendar (walkthrough 12A)", async () => {
    renderApp();
    expect(document.querySelector(".audiogram-app").textContent).toContain(
      "照報告上的日期填。報告寫西元的話，2026 年就是民國 115 年。",
    );
    for (const name of ["民國年", "月", "日"]) {
      expect(screen.getByLabelText(name).getAttribute("inputmode")).toBe("numeric");
    }
    typeDate("115", "10", "1");
    forward();
    drag(1000, 40, 40);
    confirmAndSave();
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(JSON.parse(fetch.mock.calls[0][1].body).tested_on).toBe("2026-10-01");
  });

  it("says a date that is not on the calendar, or half typed, is not right (walkthrough 12A)", () => {
    for (const [year, month, day] of [["115", "2", "30"], ["115", "", ""], ["一一五", "1", "1"]]) {
      cleanup();
      renderApp();
      typeDate(year, month, day);
      forward();
      drag(1000, 40, 40);
      confirmAndSave();
      expect(screen.getByRole("alert").textContent).toContain("檢查日期不對，請照報告再填一次");
    }
    expect(fetch).not.toHaveBeenCalled();
  });

  it("needs a date that is not in the future (acceptance 13)", () => {
    renderRight();
    drag(1000, 40, 40);
    confirmAndSave();
    expect(screen.getByRole("alert").textContent).toContain("請填寫檢查日期");
    fireEvent.click(screen.getByRole("button", { name: "改日期" }));
    setDate("2026-10-17");
    confirmAndSave();
    expect(screen.getByRole("alert").textContent).toContain("檢查日期不能是未來");
    expect(fetch).not.toHaveBeenCalled();
    expect(point("right-air-1000")).not.toBeNull();
  });

  it("needs at least one point (acceptance 14)", () => {
    renderApp();
    setDate(TODAY);
    confirmAndSave();
    expect(screen.getByRole("alert").textContent).toContain("請至少標記一個點");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("a double click sends once; a retry reuses the receipt number (acceptance 15)", async () => {
    fetch.mockImplementationOnce(() => Promise.reject(new Error("offline")));
    renderApp();
    setDate(TODAY);
    forward();
    drag(1000, 40, 40);
    confirmAndSave();
    // C1 on the loading comparison page: 存檔中… with a spinner, and it cannot be pressed again.
    const saving = screen.getByRole("button", { name: "存檔中…" });
    expect(saving.disabled).toBe(true);
    expect(saving.querySelector(".spinner").getAttribute("aria-hidden")).toBe("true");
    fireEvent.click(saving);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("存檔失敗"));
    expect(fetch).toHaveBeenCalledTimes(1);
    save();
    await waitFor(() => expect(navigate).toHaveBeenCalled());
    const keys = fetch.mock.calls.map(([, options]) => options.headers["Idempotency-Key"]);
    expect(keys[1]).toBe(keys[0]);
  });

  it("shows a point's error, which DRF nests by index (review 1-3)", async () => {
    fetch.mockImplementationOnce(() =>
      Promise.resolve({
        ok: false,
        status: 400,
        json: () => Promise.resolve({ points: { 0: { non_field_errors: ["這個頻率不能標記"] } } }),
      }),
    );
    renderApp();
    setDate(TODAY);
    forward();
    drag(1000, 40, 40);
    confirmAndSave();
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("這個頻率不能標記"));
  });

  it("shows the server's reasons on 400", async () => {
    fetch.mockImplementationOnce(() =>
      Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({ tested_on: ["檢查日期不能是未來"] }) }),
    );
    renderApp();
    setDate(TODAY);
    forward();
    drag(1000, 40, 40);
    confirmAndSave();
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("檢查日期不能是未來"));
    expect(navigate).not.toHaveBeenCalled();
  });
});

// Spec docs/specs/phase-05/phase5_audiogram_2.md 4.1; #200: editing walks the same four steps.
describe("edit", () => {
  const SAVED = [
    { ear: "right", conduction: "air", frequency: 1000, db: 40, no_response: false, masked: true },
    { ear: "right", conduction: "air", frequency: 2000, db: 120, no_response: true, masked: false },
  ];
  const renderEdit = () =>
    render(
      <AudiogramApp
        today={TODAY}
        csrfToken="csrf-token"
        navigate={navigate}
        audiogramId={7}
        initialPoints={SAVED}
        initialTestedOn="2026-01-10"
      />,
    );
  const sent = () => JSON.parse(fetch.mock.calls[0][1].body);

  it("opens with the saved points and date, in four steps (acceptance 1, #200 acceptance 2)", () => {
    renderEdit();
    expect(progress()).toBe("第 1 步／共 4 步：檢查日期");
    expect(screen.getByLabelText("民國年").value).toBe("115");
    expect(screen.getByLabelText("月").value).toBe("1");
    expect(screen.getByLabelText("日").value).toBe("10");
    forward();
    expect(point("right-air-1000").dataset.masked).toBe("true");
    expect(point("right-air-1000").querySelector("polygon")).not.toBeNull();
    expect(point("right-air-2000").dataset.noResponse).toBe("true");
    expect(point("right-air-2000").querySelector(".no-response-arrow")).not.toBeNull();
    expect(select("右耳氣導 1000 Hz").value).toBe("40");
    expect(maskBox("右耳氣導 1000 Hz").checked).toBe(true);
    expect(select("右耳氣導 2000 Hz").value).toBe("nr");
  });

  it("the clear button waits for a newly marked point (spec 4.1)", () => {
    renderEdit();
    forward();
    const clear = () => screen.getByRole("button", { name: /清除/ });
    expect(clear().disabled).toBe(true);
    drag(500, 20, 20);
    expect(clear().textContent).toBe("清除 右耳氣導 500 Hz");
  });

  it("puts the whole audiogram, then opens it (acceptance 2)", async () => {
    fetch.mockImplementationOnce(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: 7 }) }),
    );
    renderEdit();
    setDate("2026-01-12");
    forward();
    // Masking is off, so moving the masked point also unmasks it.
    drag(1000, 40, 60);
    fireEvent.change(select("右耳氣導 2000 Hz"), { target: { value: "" } });
    confirmAndSave();
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/audiograms/7"));
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("/api/audiograms/7/");
    expect(options.method).toBe("PUT");
    expect(options.headers["X-CSRFToken"]).toBe("csrf-token");
    expect(options.headers["Idempotency-Key"]).toBeUndefined();
    expect(sent()).toEqual({
      tested_on: "2026-01-12",
      points: [{ ear: "right", conduction: "air", frequency: 1000, db: 60, no_response: false, masked: false }],
    });
  });

  it("checks the date and points before sending (acceptance 3)", () => {
    renderEdit();
    setDate("2026-10-17");
    confirmAndSave();
    expect(screen.getByRole("alert").textContent).toContain("檢查日期不能是未來");
    fireEvent.click(screen.getByRole("button", { name: "改日期" }));
    setDate("2026-01-10");
    forward();
    fireEvent.change(select("右耳氣導 1000 Hz"), { target: { value: "" } });
    fireEvent.change(select("右耳氣導 2000 Hz"), { target: { value: "" } });
    confirmAndSave();
    expect(screen.getByRole("alert").textContent).toContain("請至少標記一個點");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("a double click sends once (acceptance 7)", async () => {
    renderEdit();
    confirmAndSave();
    fireEvent.click(screen.getByRole("button", { name: "存檔中…" }));
    await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("says so when the audiogram is gone", async () => {
    fetch.mockImplementationOnce(() => Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) }));
    renderEdit();
    confirmAndSave();
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("這張聽力圖已經不存在"));
    expect(navigate).not.toHaveBeenCalled();
  });
});

// #617 (spec #611 K1): the last point of this step, large, right over the chart.
describe("reading over the chart (#617)", () => {
  // The one over the chart, not the one in #618's demo.
  const reading = () => document.querySelector(".audiogram-app > .audiogram-reading");
  const shown = () => [...reading().children].map((row) => row.textContent);
  const said = () => screen.getByRole("status").textContent;
  const HINT = ["點一下圖來標記"];

  it("says where to tap on both ear steps, right over the chart, and not on the confirm step (acceptance 31, 40)", () => {
    renderRight();
    expect(shown()).toEqual(HINT);
    expect(reading().nextElementSibling.classList.contains("audiogram-chart")).toBe(true);
    expect(said()).toBe("");
    forward();
    expect(shown()).toEqual(HINT);
    forward();
    expect(progress()).toBe("第 4 步／共 4 步：確認存檔");
    expect(reading()).toBeNull();
  });

  it("writes the point once released, masked and no response too (acceptance 32, 33)", () => {
    renderRight();
    drag(1000, 45, 45);
    expect(shown()).toEqual(["右耳氣導", "1000 Hz　45 dB"]);
    expect(said()).toBe("右耳氣導　1000 Hz　45 dB");
    fireEvent.click(maskToggle());
    drag(2000, 60, 60);
    expect(shown()).toEqual(["右耳氣導", "2000 Hz　60 dB　遮蔽"]);
    forward();
    pickSymbol("左耳骨導");
    drag(4000, 60, 95);
    expect(shown()).toEqual(["左耳骨導", "4000 Hz　無反應"]);
    expect(said()).toBe("左耳骨導　4000 Hz　無反應");
  });

  it("follows the finger while dragging, and the status area is written only on release (acceptance 34)", () => {
    renderRight();
    drag(500, 30, 30);
    expect(said()).toBe("右耳氣導　500 Hz　30 dB");
    press(2000, 40);
    expect(shown()).toEqual(["右耳氣導", "2000 Hz　40 dB"]);
    move(2000, 55);
    expect(shown()).toEqual(["右耳氣導", "2000 Hz　55 dB"]);
    move(2000, 135);
    expect(shown()).toEqual(["右耳氣導", "2000 Hz　無反應"]);
    expect(said()).toBe("右耳氣導　500 Hz　30 dB");
    release(2000, 70);
    expect(shown()).toEqual(["右耳氣導", "2000 Hz　70 dB"]);
    expect(said()).toBe("右耳氣導　2000 Hz　70 dB");
  });

  it("goes back to the last point when a drag is called off", () => {
    renderRight();
    drag(500, 30, 30);
    press(2000, 40);
    fireEvent.pointerCancel(chart(), at(2000, 40));
    expect(shown()).toEqual(["右耳氣導", "500 Hz　30 dB"]);
    expect(said()).toBe("右耳氣導　500 Hz　30 dB");
  });

  it("goes back to the hint when the point is deleted, three ways (acceptance 35)", () => {
    for (const remove of [
      () => drag(1000, 45, 45),
      () => fireEvent.click(screen.getByRole("button", { name: "清除 右耳氣導 1000 Hz" })),
      () => fireEvent.change(select("右耳氣導 1000 Hz"), { target: { value: "" } }),
    ]) {
      cleanup();
      renderRight();
      drag(1000, 45, 45);
      remove();
      expect(point("right-air-1000")).toBeNull();
      expect(shown()).toEqual(HINT);
      expect(said()).toBe("");
    }
  });

  it("starts over on the other ear's step (acceptance 36)", () => {
    renderRight();
    drag(1000, 45, 45);
    forward();
    expect(shown()).toEqual(HINT);
    expect(said()).toBe("");
    back();
    expect(shown()).toEqual(HINT);
  });

  it("writes a value picked in the table, and says it (acceptance 37)", () => {
    renderRight();
    fireEvent.change(select("右耳骨導 2000 Hz"), { target: { value: "35" } });
    expect(shown()).toEqual(["右耳骨導", "2000 Hz　35 dB"]);
    expect(said()).toBe("右耳骨導　2000 Hz　35 dB");
    fireEvent.click(maskBox("右耳骨導 2000 Hz"));
    expect(shown()).toEqual(["右耳骨導", "2000 Hz　35 dB　遮蔽"]);
    fireEvent.change(select("右耳氣導 8000 Hz"), { target: { value: "nr" } });
    expect(shown()).toEqual(["右耳氣導", "8000 Hz　無反應"]);
  });

  it("keeps the magnifier, the clear button and the count as they were (acceptance 41)", () => {
    renderRight();
    press(1000, 40);
    expect(magnifier().textContent).toBe("1000 Hz 40 dB");
    release(1000, 40);
    expect(magnifier()).toBeNull();
    expect(screen.getByRole("button", { name: "清除 右耳氣導 1000 Hz" })).toBeTruthy();
    expect(document.querySelector(".audiogram-count").textContent).toBe("右耳已標：氣導 1 個、骨導 0 個");
  });
});

describe("field names (#354)", () => {
  it("no label or legend ends in a colon, on any step", () => {
    renderApp();
    const names = [];
    const collect = () =>
      document.querySelectorAll("label, legend").forEach((el) => names.push(el.textContent.trim()));
    collect();
    while (!screen.queryByRole("button", { name: "存檔" })) {
      forward();
      collect();
    }
    expect(names).toContain("檢查日期");
    expect(names.filter((name) => /[：:]$/.test(name))).toEqual([]);
  });
});

// #465 (the #464 mockup 5A, 5B): the input's layout; marking itself is unchanged.
describe("layout (#465)", () => {
  const howto = () => document.querySelector(".audiogram-howto");
  const renderEdit = () =>
    render(<AudiogramApp today={TODAY} csrfToken="csrf-token" navigate={navigate} audiogramId={7} initialTestedOn="2026-01-10" />);

  it("shows how to mark on a new audiogram's first ear, folded under 怎麼標記 on the second", () => {
    renderRight();
    expect(howto().closest("details")).toBeNull();
    forward();
    const fold = howto().closest("details");
    expect(fold.open).toBe(false);
    expect(fold.querySelector("summary .link-card-title").textContent).toBe("怎麼標記");
    expect(fold.textContent).toContain("報告上的 O 是右耳（通常是紅色），X 是左耳（通常是藍色）");
  });

  it("folds how to mark on both ears while editing", () => {
    renderEdit();
    forward();
    expect(howto().closest("details").open).toBe(false);
    forward();
    expect(howto().closest("details").open).toBe(false);
  });

  it("says the no-response line at the body size, not 16px", () => {
    renderRight();
    expect(screen.getByText("報告上符號下面有箭頭（無反應），就往下拖出圖外。").className).not.toContain("text-base");
  });

  it("puts 存檔 and 上一步 before the folded value table on the confirm step", () => {
    renderApp();
    forward();
    forward();
    forward();
    const table = document.querySelector("details.audiogram-table");
    for (const name of ["存檔", "上一步"]) {
      const button = screen.getByRole("button", { name });
      expect(button.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it("folds the value table as a list row", () => {
    renderRight();
    const table = document.querySelector("details.audiogram-table");
    expect(table.classList.contains("result-details")).toBe(true);
    expect(table.querySelector("summary .link-card-title").textContent).toBe("用數值輸入（鍵盤或螢幕閱讀器）");
  });
});

// #618 (spec #611 K2): 看示範 under 怎麼標記 plays on a small chart of its own.
describe("demo under 怎麼標記 (#618)", () => {
  const howto = () => document.querySelector(".audiogram-howto").parentElement;
  const demoButton = () => [...howto().querySelectorAll("button")].find((b) => /看示範|再看一次/.test(b.textContent));
  const renderEdit = () =>
    render(<AudiogramApp today={TODAY} csrfToken="csrf-token" navigate={navigate} audiogramId={7} initialTestedOn="2026-01-10" />);

  it("is in how to mark on both ear steps, open or folded, new or editing (acceptance 42)", () => {
    renderRight();
    expect(demoButton().textContent).toBe("▶ 看示範");
    expect(howto().querySelector(".audiogram-demo")).not.toBeNull();
    forward();
    expect(howto().closest("details")).not.toBeNull();
    expect(demoButton().textContent).toBe("▶ 看示範");
    cleanup();
    renderEdit();
    forward();
    expect(demoButton()).toBeDefined();
    forward();
    expect(demoButton()).toBeDefined();
    forward();
    expect(document.querySelector(".audiogram-demo")).toBeNull();
  });

  it("leaves the user's points, the count and the reading over the chart as they were (acceptance 46)", () => {
    vi.useFakeTimers();
    renderRight();
    drag(2000, 60, 60);
    const userReading = () => [...document.querySelector(".audiogram-app > .audiogram-reading").children].map((row) => row.textContent);
    fireEvent.click(demoButton());
    act(() => vi.advanceTimersByTime(2100));
    expect(demoButton().textContent).toBe("↺ 再看一次");
    expect(chart().querySelectorAll("[data-point]")).toHaveLength(1);
    expect(point("right-air-2000").dataset.db).toBe("60");
    expect(document.querySelector(".audiogram-count").textContent).toBe("右耳已標：氣導 1 個、骨導 0 個");
    expect(userReading()).toEqual(["右耳氣導", "2000 Hz　60 dB"]);
    expect(screen.getByRole("status").textContent).toBe("右耳氣導　2000 Hz　60 dB");
    expect(screen.getByRole("button", { name: "清除 右耳氣導 2000 Hz" })).toBeTruthy();
  });

  it("starts again on the other ear's step, with that ear's symbol", () => {
    vi.useFakeTimers();
    renderEdit();
    forward();
    fireEvent.click(demoButton());
    act(() => vi.advanceTimersByTime(2100));
    forward();
    expect(demoButton().textContent).toBe("▶ 看示範");
    expect(document.querySelector(".audiogram-demo-mark")).toBeNull();
  });

  it("has no button with reduced motion, the words as they were (acceptance 47)", () => {
    reduceMotion = true;
    renderRight();
    expect(demoButton()).toBeUndefined();
    expect(document.querySelector(".audiogram-demo")).toBeNull();
    expect([...document.querySelectorAll(".audiogram-howto .step-list-body")].map((li) => li.textContent)).toEqual([
      "選下面的符號",
      "在圖上按住，上下拖到報告上的位置",
      "放開就標好了；標錯就在那個點上點一下，可以刪除",
    ]);
    expect(screen.getByText("報告上符號下面有箭頭（無反應），就往下拖出圖外。")).toBeTruthy();
  });
});

// #619 (spec #611 R1, the #613 mockup's 6A): on the confirm step, which air frequencies one ear
// has and the other has not; only a tip, never in the way of saving.
describe("missed marks on the confirm step (#619)", () => {
  const air = (ear, frequencies) =>
    frequencies.map((frequency) => ({ ear, conduction: "air", frequency, db: 40, no_response: false, masked: false }));
  const renderConfirm = (initialPoints) => {
    render(
      <AudiogramApp
        today={TODAY}
        csrfToken="csrf-token"
        navigate={navigate}
        audiogramId={7}
        initialPoints={initialPoints}
        initialTestedOn="2026-01-10"
      />,
    );
    forward();
    forward();
    forward();
  };
  const tip = () => document.querySelector(".audiogram-missed");
  const sentences = () => [...tip().querySelectorAll("p")].map((p) => p.textContent);
  const SIX = [250, 500, 1000, 2000, 4000, 8000];
  const LAST = "報告上本來就沒有的話，直接存檔就好。";

  it("says what the left ear is missing under the counts, over 存檔, as a tip box (acceptance 50, 59)", () => {
    renderConfirm([...air("right", SIX), ...air("left", [250, 500, 1000])]);
    expect(sentences()).toEqual(["左耳沒有標 2000、4000、8000 Hz。", LAST]);
    expect(tip().classList.contains("tip-box")).toBe(true);
    expect(tip().classList.contains("alert")).toBe(false);
    expect(tip().closest("[role=alert]")).toBeNull();
    expect(tip().querySelector("[role]")).toBeNull();
    expect(tip().querySelector("svg")).toBeNull();
    const leftCount = screen.getByText("左耳：氣導 3 個、骨導 0 個").closest("p");
    const saveButton = screen.getByRole("button", { name: "存檔" });
    expect(leftCount.compareDocumentPosition(tip()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(tip().compareDocumentPosition(saveButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("each ear missing different frequencies is a sentence each, the last one once (acceptance 52)", () => {
    renderConfirm([...air("right", [250, 500, 1000, 2000, 4000, 6000]), ...air("left", [250, 500, 1000, 8000])]);
    expect(sentences()).toEqual(["右耳沒有標 8000 Hz。", "左耳沒有標 2000、4000、6000 Hz。", LAST]);
  });

  it("no tip when the air frequencies match, or an ear has nothing marked (acceptance 53, 54)", () => {
    renderConfirm([...air("right", SIX), ...air("left", SIX)]);
    expect(tip()).toBeNull();
    cleanup();
    renderConfirm(air("right", SIX));
    expect(tip()).toBeNull();
    expect(screen.getByText("左耳：還沒有標任何點")).toBeTruthy();
  });

  it("is above the error list, and saves as usual with it shown (acceptance 57)", async () => {
    renderConfirm([...air("right", SIX), ...air("left", [250, 500, 1000])]);
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: false, status: 500 }));
    save();
    const error = await screen.findByRole("alert");
    expect(tip().compareDocumentPosition(error) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(error.textContent).not.toContain("沒有標");
    expect(fetch).toHaveBeenCalledTimes(1);
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: 7 }) }));
    save();
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/audiograms/7"));
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("follows marks added on the way back, and goes once they match (acceptance 58)", () => {
    renderConfirm([...air("right", SIX), ...air("left", [250, 500, 1000])]);
    fireEvent.click(screen.getByRole("button", { name: "改左耳" }));
    pickSymbol("左耳氣導");
    drag(2000, 40, 40);
    forward();
    expect(sentences()).toEqual(["左耳沒有標 4000、8000 Hz。", LAST]);
    fireEvent.click(screen.getByRole("button", { name: "改左耳" }));
    pickSymbol("左耳氣導");
    drag(4000, 40, 40);
    drag(8000, 40, 40);
    forward();
    expect(tip()).toBeNull();
  });
});

// Spec #611 N3 (acceptance 28), ticket #616: 年 and 月 say 下一個 on the phone keyboard and
// Enter there moves on; 日 is the last, and with no sending on that step Enter still does nothing.
describe("Enter in the date (#616)", () => {
  const part = (name) => screen.getByLabelText(name);
  // fireEvent returns false when the app stopped what Enter would do.
  const enter = (name, init = {}) => {
    part(name).focus();
    return fireEvent.keyDown(part(name), { key: "Enter", ...init });
  };

  it("says 下一個 on 年 and 月, not on 日", () => {
    renderApp();
    expect(part("民國年").getAttribute("enterkeyhint")).toBe("next");
    expect(part("月").getAttribute("enterkeyhint")).toBe("next");
    expect(part("日").hasAttribute("enterkeyhint")).toBe(false);
  });

  it("goes 年 to 月 to 日, and 日 stays as it was", () => {
    renderApp();
    expect(enter("民國年")).toBe(false);
    expect(document.activeElement).toBe(part("月"));
    expect(enter("月")).toBe(false);
    expect(document.activeElement).toBe(part("日"));
    expect(enter("日")).toBe(true);
    expect(document.activeElement).toBe(part("日"));
    expect(progress()).toBe("第 1 步／共 4 步：檢查日期");
  });

  it("leaves the Enter that picks a character alone", () => {
    renderApp();
    expect(enter("民國年", { isComposing: true })).toBe(true);
    expect(document.activeElement).toBe(part("民國年"));
    expect(enter("月", { keyCode: 229 })).toBe(true);
    expect(document.activeElement).toBe(part("月"));
  });
});
