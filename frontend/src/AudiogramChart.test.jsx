import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import AudiogramChart from "./AudiogramChart.jsx";
import { CHART, x, y } from "./audiogram.js";

afterEach(cleanup);

it("the read-only chart draws 0 and -10 where they belong (acceptance 17)", () => {
  const points = [
    { ear: "right", conduction: "air", frequency: 1000, db: 0, no_response: false },
    { ear: "right", conduction: "air", frequency: 2000, db: -10, no_response: false },
  ];
  const { container } = render(<AudiogramChart points={points} />);
  const circle = (key) => container.querySelector(`[data-point="${key}"] circle`);
  expect(Number(circle("right-air-1000").getAttribute("cx"))).toBe(x(1000));
  expect(Number(circle("right-air-1000").getAttribute("cy"))).toBe(y(0));
  expect(Number(circle("right-air-2000").getAttribute("cy"))).toBe(y(-10));
  // Read-only: no dragging, so the page scrolls normally.
  expect(container.querySelector("svg").style.touchAction).toBe("");
});

it("draws each masked mark (acceptance 40)", () => {
  const masked = (ear, conduction) => ({ ear, conduction, frequency: 1000, db: 40, no_response: false, masked: true });
  const { container } = render(
    <AudiogramChart points={[masked("right", "air"), masked("left", "air"), masked("right", "bone"), masked("left", "bone")]} />,
  );
  const mark = (key) => container.querySelector(`[data-point="${key}"]`);
  expect(mark("right-air-1000").querySelector("polygon").getAttribute("points").split(" ")).toHaveLength(3);
  expect(mark("left-air-1000").querySelector("rect")).not.toBeNull();
  expect(mark("right-bone-1000").querySelector("text").textContent).toBe("[");
  expect(mark("left-bone-1000").querySelector("text").textContent).toBe("]");
});

// Spec docs/specs/phase-05/phase5_audiogram_2.md 4.2, acceptance 22: the older test underneath, light and dashed.
it("draws an older audiogram light and dashed under the newer one", () => {
  const air = (frequency, db) => ({ ear: "right", conduction: "air", frequency, db, no_response: false, masked: false });
  const bone = { ear: "right", conduction: "bone", frequency: 1000, db: 20, no_response: false, masked: false };
  const { container } = render(
    <AudiogramChart points={[air(500, 40), air(1000, 45), bone]} oldPoints={[air(500, 30), air(1000, 35), bone]} />,
  );
  const newer = container.querySelector(".audiogram-new");
  const older = container.querySelector(".audiogram-old");
  expect(newer.querySelector("polyline").getAttribute("stroke")).toBe("#c0392b");
  expect(newer.querySelector("polyline").getAttribute("stroke-dasharray")).toBeNull();
  expect(older.querySelector("polyline").getAttribute("stroke")).toBe("#cc5f56");
  expect(older.querySelector("polyline").getAttribute("stroke-dasharray")).not.toBeNull();
  expect(older.querySelector('[data-point="right-air-500"] circle').getAttribute("stroke")).toBe("#cc5f56");
  expect(older.querySelector('[data-point="right-bone-1000"] text').getAttribute("fill")).toBe("#cc5f56");
  expect(newer.querySelector('[data-point="right-bone-1000"] text').getAttribute("fill")).toBe("#c0392b");
  // The newer one is drawn last, so it sits on top.
  expect(older.compareDocumentPosition(newer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

it("the left ear's older audiogram is light blue", () => {
  const point = { ear: "left", conduction: "air", frequency: 500, db: 30, no_response: false, masked: false };
  const { container } = render(<AudiogramChart points={[point]} oldPoints={[point]} />);
  expect(container.querySelector('.audiogram-old [data-point="left-air-500"] path').getAttribute("stroke")).toBe("#5980b5");
});

it("draws the green normal range down to 25 dB, under everything else", () => {
  const { container } = render(<AudiogramChart points={[]} />);
  const band = container.querySelector('rect[fill="#e9f5ec"]');
  expect(Number(band.getAttribute("y"))).toBe(y(-10));
  expect(Number(band.getAttribute("height"))).toBe(y(25) - y(-10));
  expect(container.querySelector("svg").firstElementChild).toBe(band);
});

// #617 (spec #611 K1): the point under a marking finger goes out as it moves, null on release.
it("passes the point under the finger to onPreview while dragging", () => {
  SVGElement.prototype.getBoundingClientRect = () => ({ left: 0, top: 0, width: CHART.width, height: CHART.height });
  const symbol = { ear: "left", conduction: "air" };
  const onPreview = vi.fn();
  const onCommit = vi.fn();
  const { container } = render(<AudiogramChart points={[]} symbol={symbol} masked onCommit={onCommit} onPreview={onPreview} />);
  const at = (db) => ({ clientX: x(1000), clientY: y(db), pointerId: 1 });
  const svg = container.querySelector("svg");
  fireEvent.pointerDown(svg, at(40));
  fireEvent.pointerMove(svg, at(50));
  expect(onPreview.mock.calls).toEqual([
    [{ ear: "left", conduction: "air", frequency: 1000, db: 40, no_response: false, masked: true }],
    [{ ear: "left", conduction: "air", frequency: 1000, db: 50, no_response: false, masked: true }],
  ]);
  fireEvent.pointerUp(svg, at(50));
  expect(onPreview).toHaveBeenLastCalledWith(null);
  expect(onCommit).toHaveBeenCalledWith(1000, { db: 50, noResponse: false });
});

it("without oldPoints nothing extra is drawn", () => {
  const { container } = render(
    <AudiogramChart points={[{ ear: "right", conduction: "air", frequency: 500, db: 30, no_response: false }]} />,
  );
  expect(container.querySelector(".audiogram-old")).toBeNull();
});

// Spec #702 (#703 mockup 7A): Apple's values are 1 dB apart and may be below -10; the chart grows
// a row up to -20 only when one is, and every other chart stays as on a clinic's report.
it("grows up to -20 only for a point below -10, and draws 1 dB values where they fall", () => {
  const air = (frequency, db) => ({ ear: "right", conduction: "air", frequency, db, no_response: false });
  const grid = (container) => [...container.querySelectorAll("svg text")].map((t) => t.textContent);
  const { container } = render(<AudiogramChart points={[air(1000, 9), air(8000, -14)]} />);
  const svg = container.querySelector("svg");
  const row = y(-10) - y(-20);
  expect(svg.getAttribute("viewBox")).toBe(`0 ${-row} ${CHART.width} ${CHART.height + row}`);
  expect(grid(container)).toContain("-20");
  const circle = (key) => container.querySelector(`[data-point="${key}"] circle`);
  expect(Number(circle("right-air-1000").getAttribute("cy"))).toBe(y(9));
  expect(Number(circle("right-air-8000").getAttribute("cy"))).toBe(y(-14));
  // The frame and the frequency numbers move up with it.
  expect(Number(container.querySelector(".audiogram-frame").getAttribute("y"))).toBe(y(-20));
  cleanup();

  const { container: usual } = render(<AudiogramChart points={[air(1000, 9), air(8000, -10)]} />);
  expect(usual.querySelector("svg").getAttribute("viewBox")).toBe(`0 0 ${CHART.width} ${CHART.height}`);
  expect(grid(usual)).not.toContain("-20");
  expect(Number(usual.querySelector(".audiogram-frame").getAttribute("y"))).toBe(CHART.top);
});

it("aligns the magnifier with the -20 dB rise and anchors edge frequencies inward", () => {
  const air = (frequency, db) => ({ ear: "right", conduction: "air", frequency, db, no_response: false });
  const row = y(-10) - y(-20);
  const symbol = { ear: "right", conduction: "air" };
  SVGElement.prototype.getBoundingClientRect = () => ({ left: 0, top: 0, width: CHART.width, height: CHART.height + row });
  const { container } = render(
    <AudiogramChart points={[air(1000, -14)]} symbol={symbol} onCommit={vi.fn()} />,
  );
  const svg = container.querySelector("svg");
  const checkAt = (frequency, db) => {
    const point = { clientX: x(frequency), clientY: y(db) + row, pointerId: 1 };
    fireEvent.pointerDown(svg, point);
    const box = container.querySelector(".audiogram-magnifier");
    const result = { edge: box.getAttribute("data-edge"), top: box.style.top };
    fireEvent.pointerUp(svg, point);
    return result;
  };

  expect(checkAt(250, 40)).toEqual({
    edge: "left",
    top: `${((y(40) + row) / (CHART.height + row)) * 100}%`,
  });
  expect(checkAt(1000, 40).edge).toBe("center");
  expect(checkAt(8000, 40).edge).toBe("right");
});
