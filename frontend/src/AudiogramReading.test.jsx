import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import AudiogramReading, { readingText } from "./AudiogramReading.jsx";

afterEach(cleanup);

const point = (overrides) => ({ ear: "right", conduction: "air", frequency: 1000, db: 45, no_response: false, masked: false, ...overrides });
const rows = (container) => [...container.querySelector(".audiogram-reading").children].map((row) => row.textContent);

// #617 (spec #611 K1, the #613 mockup's B): the symbol's name over the frequency and level.
describe("AudiogramReading", () => {
  it("says where to tap while nothing is marked (acceptance 31)", () => {
    const { container } = render(<AudiogramReading point={null} />);
    expect(rows(container)).toEqual(["點一下圖來標記"]);
  });

  it("writes the symbol's name, then the frequency and the level (acceptance 32)", () => {
    const { container } = render(<AudiogramReading point={point()} />);
    expect(rows(container)).toEqual(["右耳氣導", "1000 Hz　45 dB"]);
  });

  it("adds 遮蔽, and writes 無反應 for the level (acceptance 33)", () => {
    const { container } = render(
      <AudiogramReading point={point({ ear: "left", conduction: "bone", frequency: 4000, db: 80, no_response: true, masked: true })} />,
    );
    expect(rows(container)).toEqual(["左耳骨導", "4000 Hz　無反應　遮蔽"]);
  });

  it("gives the same point as one line for the status area", () => {
    expect(readingText(point())).toBe("右耳氣導　1000 Hz　45 dB");
    expect(readingText(point({ ear: "left", frequency: 250, db: -10, masked: true }))).toBe("左耳氣導　250 Hz　-10 dB　遮蔽");
  });
});
