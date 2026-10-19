import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import AudiogramChart from "./AudiogramChart.jsx";
import { x, y } from "./audiogram.js";

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
  expect(older.querySelector("polyline").getAttribute("stroke")).toBe("#e8a59d");
  expect(older.querySelector("polyline").getAttribute("stroke-dasharray")).not.toBeNull();
  expect(older.querySelector('[data-point="right-air-500"] circle').getAttribute("stroke")).toBe("#e8a59d");
  expect(older.querySelector('[data-point="right-bone-1000"] text').getAttribute("fill")).toBe("#e8a59d");
  expect(newer.querySelector('[data-point="right-bone-1000"] text').getAttribute("fill")).toBe("#c0392b");
  // The newer one is drawn last, so it sits on top.
  expect(older.compareDocumentPosition(newer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

it("the left ear's older audiogram is light blue", () => {
  const point = { ear: "left", conduction: "air", frequency: 500, db: 30, no_response: false, masked: false };
  const { container } = render(<AudiogramChart points={[point]} oldPoints={[point]} />);
  expect(container.querySelector('.audiogram-old [data-point="left-air-500"] path').getAttribute("stroke")).toBe("#9db5d6");
});

it("without oldPoints nothing extra is drawn", () => {
  const { container } = render(
    <AudiogramChart points={[{ ear: "right", conduction: "air", frequency: 500, db: 30, no_response: false }]} />,
  );
  expect(container.querySelector(".audiogram-old")).toBeNull();
});
