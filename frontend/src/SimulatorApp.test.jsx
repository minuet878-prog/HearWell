import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import SimulatorApp from "./SimulatorApp.jsx";

afterEach(cleanup);

const FREQUENCIES = [250, 500, 1000, 2000, 4000, 8000];
const HIGH_NOTE = "選的是高頻下降：檢查報告上的平均可能只寫「輕度」…";
const DATA = {
  frequencies: FREQUENCIES,
  levels: [
    { code: "high-frequency", name: "高頻下降", line: "尖細的聲音大多聽不到", thresholds: [15, 20, 25, 45, 65, 75], note: HIGH_NOTE },
    { code: "mild", name: "輕度", line: "小聲就漏聽", thresholds: [25, 30, 30, 35, 40, 40] },
    { code: "moderate", name: "中度", line: "常聽不完整", thresholds: [40, 45, 50, 55, 60, 65] },
    { code: "moderately-severe", name: "中重度", line: "不大聲聽不到", thresholds: [55, 60, 65, 70, 75, 80] },
  ],
  normal: "每一種聲音都聽得到",
  sentences: [
    { text: "星期四下午三點去看醫生。", voice: "女", audio: "/static/s1.m4a" },
    { text: "這個藥飯後吃，一天三次。", voice: "男", audio: "/static/s2.m4a" },
    { text: "孫子說下禮拜六要回來吃飯。", voice: "女", audio: "/static/s3.m4a" },
    { text: "謝謝你送的水果，很新鮮。", voice: "男", audio: "/static/s4.m4a" },
  ],
  limits: ["這是典型的程度，不是誰真正的聽力。", "聽不到聲音？先關掉手機的靜音。"],
};

// Stands in for Web Audio: records what the player asked for.
function fakeEngine() {
  return {
    calls: [],
    ended: null,
    play(url, onEnded) {
      this.calls.push(["play", url]);
      this.ended = onEnded;
    },
    stop() {
      this.calls.push(["stop"]);
    },
    setBands(bands) {
      this.calls.push(["bands", bands.map((band) => band.gain)]);
    },
    played() {
      return this.calls.filter(([what]) => what === "play").map(([, url]) => url);
    },
    lastGains() {
      return this.calls.filter(([what]) => what === "bands").at(-1)[1];
    },
  };
}

function open() {
  const engine = fakeEngine();
  const view = render(<SimulatorApp data={DATA} engine={engine} />);
  return { engine, ...view };
}

const press = (name) => fireEvent.click(screen.getByRole("button", { name }));
const pressed = (group) =>
  within(screen.getByRole("group", { name: group }))
    .getAllByRole("button")
    .filter((b) => b.getAttribute("aria-pressed") === "true")
    .map((b) => b.textContent);
const lit = (container) => [...container.querySelectorAll(".simulator-bar")].map((bar) => bar.querySelectorAll(".is-lit").length);
const line = (container) => container.querySelector(".simulator-line").textContent;
const caption = (container) => container.querySelector(".simulator-caption").textContent;

it("opens silent on 高頻下降 and 模擬, its bars and its bands", () => {
  // #484 acceptance 4 and 21: nothing plays or loads before the play button.
  const { engine, container } = open();
  expect(engine.played()).toEqual([]);
  expect(pressed("程度")).toEqual(["高頻下降"]);
  expect(pressed("怎麼聽")).toEqual(["模擬"]);
  expect(line(container)).toBe("高頻下降：尖細的聲音大多聽不到");
  expect(lit(container)).toEqual([7, 6, 6, 4, 3, 2]);
  expect(engine.lastGains()).toEqual([-15, -20, -25, -45, -65, -75]);
  expect(caption(container)).toBe("第 1 句・女聲（共 4 句）");
});

it("plays the sentence and offers to pause it", () => {
  // #484 acceptance 5.
  const { engine } = open();
  press("中度");
  press("播放");
  expect(engine.played()).toEqual(["/static/s1.m4a"]);
  expect(engine.lastGains()).toEqual([-40, -45, -50, -55, -60, -65]);
  press("暫停");
  expect(engine.calls.at(-1)).toEqual(["stop"]);
  expect(screen.getByRole("button", { name: "播放" })).toBeTruthy();
});

it("changes degree while playing without stopping or starting again", () => {
  // #484 acceptance 7.
  const { engine, container } = open();
  press("中度");
  press("播放");
  const before = engine.calls.length;
  press("輕度");
  const after = engine.calls.slice(before);
  expect(after.filter(([what]) => what !== "bands")).toEqual([]);
  expect(engine.lastGains()).toEqual([-25, -30, -30, -35, -40, -40]);
  expect(line(container)).toBe("輕度：小聲就漏聽");
  expect(screen.getByRole("button", { name: "暫停" })).toBeTruthy();
});

it("switches to 正常聽 and back while playing, the bars full, without starting again", () => {
  // #484 acceptance 8.
  const { engine, container } = open();
  press("播放");
  const before = engine.calls.length;
  press("正常聽");
  expect(engine.lastGains()).toEqual([0, 0, 0, 0, 0, 0]);
  expect(line(container)).toBe("正常聽：每一種聲音都聽得到");
  expect(lit(container)).toEqual([8, 8, 8, 8, 8, 8]);
  // The degree stays picked for when 模擬 comes back.
  expect(pressed("程度")).toEqual(["高頻下降"]);
  press("模擬");
  expect(engine.lastGains()).toEqual([-15, -20, -25, -45, -65, -75]);
  expect(engine.calls.slice(before).filter(([what]) => what !== "bands")).toEqual([]);
});

it("goes back to 模擬 when a degree is picked during 正常聽", () => {
  // #484 acceptance 9.
  const { engine } = open();
  press("正常聽");
  press("中重度");
  expect(pressed("怎麼聽")).toEqual(["模擬"]);
  expect(engine.lastGains()).toEqual([-55, -60, -65, -70, -75, -80]);
});

it("plays the next sentence instead when moving on while playing, and wraps round", () => {
  // #484 acceptance 6; the #485 mockup: 上一句 on the first goes to the fourth.
  const { engine, container } = open();
  press("播放");
  press("下一句");
  expect(engine.played()).toEqual(["/static/s1.m4a", "/static/s2.m4a"]);
  expect(caption(container)).toBe("第 2 句・男聲（共 4 句）");
  press("暫停");
  press("上一句");
  press("上一句");
  expect(caption(container)).toBe("第 4 句・男聲（共 4 句）");
  // Not playing: moving only changes the sentence.
  expect(engine.played()).toEqual(["/static/s1.m4a", "/static/s2.m4a"]);
});

it("goes back to 播放 when a sentence ends, without playing the next", () => {
  const { engine } = open();
  press("播放");
  act(() => engine.ended());
  expect(screen.getByRole("button", { name: "播放" })).toBeTruthy();
  expect(engine.played()).toEqual(["/static/s1.m4a"]);
});

it("shows the sentence only when asked, and folds it again for the next one", () => {
  // #484 acceptance 12 and 13.
  open();
  expect(screen.queryByText("星期四下午三點去看醫生。")).toBeNull();
  const reveal = screen.getByRole("button", { name: "顯示這句話" });
  expect(reveal.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(reveal);
  expect(screen.getByText("星期四下午三點去看醫生。")).toBeTruthy();
  const fold = screen.getByRole("button", { name: "收起這句話" });
  expect(fold.getAttribute("aria-expanded")).toBe("true");
  press("下一句");
  expect(screen.queryByText("這個藥飯後吃，一天三次。")).toBeNull();
  expect(screen.getByRole("button", { name: "顯示這句話" })).toBeTruthy();
});

it("tells the limits always and the 高頻下降 note only on 高頻下降", () => {
  // #484 acceptance 14 and 15; the #485 pick for the note.
  const { container } = open();
  const hint = () => container.querySelector(".tip-box").textContent;
  expect(hint()).toContain(HIGH_NOTE);
  for (const limit of DATA.limits) expect(hint()).toContain(limit);
  press("輕度");
  expect(hint()).not.toContain(HIGH_NOTE);
  for (const limit of DATA.limits) expect(hint()).toContain(limit);
});

it("announces the line that says what is heard", () => {
  // #484 acceptance 20: the bars are drawn, the line says it.
  const { container } = open();
  expect(container.querySelector(".simulator-line").getAttribute("aria-live")).toBe("polite");
  expect(container.querySelector(".simulator-bars").getAttribute("aria-hidden")).toBe("true");
});
