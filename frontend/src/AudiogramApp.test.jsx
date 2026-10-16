import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
afterEach(cleanup);

const renderApp = () =>
  render(<AudiogramApp today={TODAY} csrfToken="csrf-token" navigate={navigate} />);
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
const maskToggle = () => screen.getByRole("button", { name: /^遮蔽：/ });
const framed = () => chart().closest(".audiogram-chart").classList.contains("masking");
const maskBox = (name) => screen.getByRole("checkbox", { name: `${name} 遮蔽` });

describe("input", () => {
  it("starts empty with right-ear air selected (acceptance 1)", () => {
    renderApp();
    expect(chart().querySelectorAll("[data-point]")).toHaveLength(0);
    expect(screen.getByRole("button", { name: /右耳氣導/ }).getAttribute("aria-pressed")).toBe("true");
    expect(maskToggle().getAttribute("aria-pressed")).toBe("false");
    expect(maskToggle().textContent).toBe("遮蔽：關");
    expect(framed()).toBe(false);
    expect(screen.getByText("再點一下同一個點可以刪除")).toBeTruthy();
    expect(screen.getByRole("button", { name: /清除/ }).disabled).toBe(true);
    expect(screen.getByLabelText("檢查日期").getAttribute("max")).toBe(TODAY);
  });

  it("drags a point into place with a magnifier (acceptance 2)", () => {
    renderApp();
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
    renderApp();
    press(1000, 40);
    expect(magnifier().dataset.place).toBe("above");
    move(1000, -10);
    expect(magnifier().dataset.place).toBe("beside");
    release(1000, -10);
  });

  it("keeps the frequency chosen on press (acceptance 3)", () => {
    renderApp();
    press(1000, 40);
    release(2000, 40);
    expect(point("right-air-1000")).not.toBeNull();
    expect(point("right-air-2000")).toBeNull();
  });

  it("moves an existing point (acceptance 4)", () => {
    renderApp();
    drag(1000, 40, 40);
    drag(1000, 40, 60);
    expect(chart().querySelectorAll("[data-point]")).toHaveLength(1);
    expect(point("right-air-1000").dataset.db).toBe("60");
  });

  it("tapping a point deletes it (acceptance 5)", () => {
    renderApp();
    drag(2000, 40, 40);
    drag(1000, 40, 40);
    press(1000, 40);
    release(1000, 40);
    expect(point("right-air-1000")).toBeNull();
    expect(point("right-air-2000")).not.toBeNull();
  });

  it("clears the last marked point (acceptance 6)", () => {
    renderApp();
    drag(500, 30, 30);
    drag(1000, 40, 40);
    const clear = screen.getByRole("button", { name: "清除 右耳氣導 1000 Hz" });
    fireEvent.click(clear);
    expect(point("right-air-1000")).toBeNull();
    expect(point("right-air-500")).not.toBeNull();
    expect(screen.getByRole("button", { name: /清除/ }).disabled).toBe(true);
  });

  it("air past the bottom is no response, not joined by the line (acceptance 7)", () => {
    renderApp();
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
    renderApp();
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
    renderApp();
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
    renderApp();
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
    renderApp();
    press(1000, 100);
    move(1000, 135);
    fireEvent.lostPointerCapture(chart(), { pointerId: 1 });
    fireEvent.pointerUp(screen.getByText("再點一下同一個點可以刪除"), at(1000, 135));
    expect(point("right-air-1000").dataset.noResponse).toBe("true");
    expect(magnifier()).toBeNull();
    // The drag is over: moving no longer drags, and a stray release on the chart changes nothing.
    move(1000, 40);
    expect(magnifier()).toBeNull();
    release(1000, 135);
    expect(point("right-air-1000").dataset.db).toBe("120");
  });

  it("dragging does not scroll the page (acceptance 11)", () => {
    renderApp();
    expect(chart().style.touchAction).toBe("none");
    const event = new Event("pointerdown", { bubbles: true, cancelable: true });
    Object.assign(event, at(1000, 40));
    chart().dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });
});

describe("masking", () => {
  it("the switch changes the marks and marks new points masked (acceptance 34)", () => {
    renderApp();
    fireEvent.click(maskToggle());
    expect(maskToggle().getAttribute("aria-pressed")).toBe("true");
    expect(maskToggle().textContent).toBe("遮蔽：開（△ □ [ ]）");
    expect(framed()).toBe(true);
    for (const [name, mark] of [["右耳氣導", "△"], ["左耳氣導", "□"], ["右耳骨導", "["], ["左耳骨導", "]"]]) {
      expect(screen.getByRole("button", { name: new RegExp(name) }).textContent).toContain(mark);
    }
    press(1000, 50);
    expect(magnifier().textContent).toBe("1000 Hz 50 dB 遮蔽");
    release(1000, 50);
    const marked = point("right-air-1000");
    expect(marked.dataset.masked).toBe("true");
    expect(marked.querySelector("polygon").getAttribute("stroke")).toBe("#c0392b");
    fireEvent.click(maskToggle());
    expect(maskToggle().textContent).toBe("遮蔽：關");
    expect(framed()).toBe(false);
    press(2000, 50);
    expect(magnifier().textContent).toBe("2000 Hz 50 dB");
    release(2000, 50);
  });

  it("tapping with the other masking converts, the next tap deletes (acceptance 35)", () => {
    renderApp();
    drag(1000, 50, 50);
    fireEvent.click(maskToggle());
    drag(1000, 50, 50);
    expect(point("right-air-1000").dataset.masked).toBe("true");
    drag(1000, 50, 50);
    expect(point("right-air-1000")).toBeNull();
  });

  it("masked and no response together (acceptance 36)", () => {
    renderApp();
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
    renderApp();
    drag(500, 30, 30);
    fireEvent.click(maskToggle());
    drag(1000, 40, 40);
    fireEvent.click(maskToggle());
    drag(2000, 50, 50);
    const lines = [...chart().querySelectorAll(".air-line-right")].map((l) => l.getAttribute("points"));
    expect(lines).toEqual([`${x(500)},${y(30)} ${x(1000)},${y(40)} ${x(2000)},${y(50)}`]);
  });

  it("the table's masking box and the chart stay in sync (acceptance 38)", () => {
    renderApp();
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
    fireEvent.click(maskToggle());
    drag(1000, 40, 40);
    setDate(TODAY);
    save();
    await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(JSON.parse(fetch.mock.calls[0][1].body).points).toEqual([
      { ear: "right", conduction: "air", frequency: 1000, db: 40, no_response: false, masked: true },
    ]);
  });
});

describe("save", () => {
  const sent = () => JSON.parse(fetch.mock.calls[0][1].body);

  it("posts the points and date, then opens the saved audiogram (acceptance 12)", async () => {
    renderApp();
    drag(1000, 40, 40);
    pickSymbol("左耳骨導");
    drag(1000, 60, 95);
    setDate("2026-10-01");
    save();
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/audiograms/42"));
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("/api/audiograms/");
    expect(options.headers["X-CSRFToken"]).toBe("csrf-token");
    expect(options.headers["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
    expect(sent().tested_on).toBe("2026-10-01");
    expect(sent().points).toEqual(
      expect.arrayContaining([
        { ear: "right", conduction: "air", frequency: 1000, db: 40, no_response: false, masked: false },
        { ear: "left", conduction: "bone", frequency: 1000, db: 80, no_response: true, masked: false },
      ]),
    );
  });

  it("needs a date that is not in the future (acceptance 13)", () => {
    renderApp();
    drag(1000, 40, 40);
    save();
    expect(screen.getByRole("alert").textContent).toContain("請填寫檢查日期");
    setDate("2026-10-17");
    save();
    expect(screen.getByRole("alert").textContent).toContain("檢查日期不能是未來");
    expect(fetch).not.toHaveBeenCalled();
    expect(point("right-air-1000")).not.toBeNull();
  });

  it("needs at least one point (acceptance 14)", () => {
    renderApp();
    setDate(TODAY);
    save();
    expect(screen.getByRole("alert").textContent).toContain("請至少標記一個點");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("a double click sends once; a retry reuses the receipt number (acceptance 15)", async () => {
    fetch.mockImplementationOnce(() => Promise.reject(new Error("offline")));
    renderApp();
    drag(1000, 40, 40);
    setDate(TODAY);
    save();
    save();
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
    drag(1000, 40, 40);
    setDate(TODAY);
    save();
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("這個頻率不能標記"));
  });

  it("shows the server's reasons on 400", async () => {
    fetch.mockImplementationOnce(() =>
      Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({ tested_on: ["檢查日期不能是未來"] }) }),
    );
    renderApp();
    drag(1000, 40, 40);
    setDate(TODAY);
    save();
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("檢查日期不能是未來"));
    expect(navigate).not.toHaveBeenCalled();
  });
});
