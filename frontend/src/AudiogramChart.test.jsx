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
