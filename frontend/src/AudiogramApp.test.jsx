import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AudiogramApp from "./AudiogramApp.jsx";
import { CHART, x, y } from "./audiogram.js";

const TODAY = "2026-10-16";
let navigate;

// jsdom has no layout: make one screen pixel equal one chart unit.
beforeEach(() => {
  navigate = vi.fn();
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
const at = (frequency, db) => ({ clientX: x(frequency), clientY: y(db), pointerId: 1 });
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
const setDate = (value) => fireEvent.change(screen.getByLabelText("檢查日期"), { target: { value } });
const save = () => fireEvent.click(screen.getByRole("button", { name: "存檔" }));
// #333 (D4): a switch named 遮蔽, with 開 or 關 written beside it.
const maskToggle = () => screen.getByRole("switch", { name: "遮蔽" });
const framed = () => chart().closest(".audiogram-chart").classList.contains("masking");
const maskBox = (name) => screen.getByRole("checkbox", { name: `${name} 遮蔽` });

describe("input", () => {
  it("starts empty with right-ear air selected (acceptance 1)", () => {
    renderApp();
    expect(screen.getByLabelText("檢查日期").getAttribute("max")).toBe(TODAY);
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

  it("dragging does not scroll the page (acceptance 11)", () => {
    renderRight();
    expect(chart().style.touchAction).toBe("none");
    const event = new Event("pointerdown", { bubbles: true, cancelable: true });
    Object.assign(event, at(1000, 40));
    chart().dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
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
});

// #199, #200 (spec #183 stories 80-93): one thing per step, checked only at the end.
describe("steps", () => {
  it("each step shows only what it needs (#199 acceptance 1)", () => {
    renderApp();
    expect(progress()).toBe("第 1 步／共 4 步：檢查日期");
    expect(screen.getByLabelText("檢查日期")).toBeTruthy();
    expect(screen.queryByRole("img", { name: /聽力圖/ })).toBeNull();
    expect(document.querySelectorAll(".step-progress-segment")).toHaveLength(4);
    expect(document.querySelectorAll(".step-progress-segment.is-done")).toHaveLength(1);

    forward();
    expect(progress()).toBe("第 2 步／共 4 步：標右耳");
    expect(screen.getByText("報告上的 O 是右耳（通常是紅色），X 是左耳（通常是藍色）")).toBeTruthy();
    expect([...document.querySelectorAll(".audiogram-howto li")].map((li) => li.textContent)).toEqual([
      "選下面的符號",
      "在圖上按住，上下拖到報告上的位置",
      "放開就標好了；標錯再點一下可以刪除",
    ]);
    expect(screen.getByText("報告上符號下面有箭頭（無反應），就往下拖出圖外。")).toBeTruthy();
    const symbols = () => [...document.querySelectorAll(".audiogram-symbol")].map((b) => b.textContent.replace(/ .*/, ""));
    expect(symbols()).toEqual(["右耳氣導", "右耳骨導"]);
    expect(screen.queryByLabelText("檢查日期")).toBeNull();
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
    expect(screen.getByLabelText("檢查日期").value).toBe("2026-01-10");
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
