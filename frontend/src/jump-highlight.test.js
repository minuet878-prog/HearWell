import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { jumpBox, setUpJumpHighlight } from "./jump-highlight.js";

// Spec #338 (ticket #343). Each test has a page of its own, at /guide: what one test sets up
// listens on its own page only.
const ADDRESS = "https://hearwell.test/guide";
let doc;

beforeEach(() => {
  doc = document.implementation.createHTMLDocument();
  doc.head.innerHTML = `<base href="${ADDRESS}">`;
  doc.body.innerHTML = `
    <a href="#main-content">跳到主要內容</a>
    <nav class="site-nav"></nav>
    <main id="main-content">
      <div id="error-summary" role="alert"><a href="#question-3">第 3 題</a></div>
      <div id="comparison-errors" role="alert"><a href="#id_aided_0">有戴的紀錄</a></div>
      <a href="#without-certificate">看沒有身障證明時</a>
      <a href="/guide/form-9#reapply">看再次申請的規定</a>
      <a href="/guide?edit=form-9#stop-form-9">修改</a>
      <section class="section-box" aria-labelledby="without-certificate">
        <h2 id="without-certificate">沒有身障證明時</h2>
      </section>
      <section class="section-box" aria-labelledby="contents-title">
        <h2 id="contents-title">選配與補助，一步一步看</h2>
        <ol class="route">
          <li class="route-stop" id="stop-form-9"><div class="route-box"></div></li>
        </ol>
      </section>
      <section data-parallel-block aria-labelledby="talk-title">
        <h2 id="talk-title">怎麼跟聽損的家人說話</h2>
        <ul class="tips tint-block"><li>先叫名字</li></ul>
      </section>
      <section aria-labelledby="share-title">
        <h2 id="share-title">把這一頁傳給家人</h2>
      </section>
      <section class="tint-block" aria-labelledby="saved-title">
        <h2 id="saved-title">聽力報告裡的組合</h2>
        <p id="saved-note">新增紀錄不會自動換掉這一組。</p>
      </section>
      <fieldset id="question-3"><legend>第 3 題</legend></fieldset>
      <input id="id_aided_0" type="radio">
    </main>`;
});

const byId = (id) => doc.getElementById(id);
const titledBy = (id) => doc.querySelector(`[aria-labelledby="${id}"]`);

// A jump lights the box its target is in (a 段落框, a 並列區塊, a route stop), or the target
// itself when it is in none.
describe("jumpBox", () => {
  it("is the 段落框 a heading titles", () => {
    expect(jumpBox(byId("without-certificate"))).toBe(titledBy("without-certificate"));
  });

  it("is the route stop itself, not the route's 段落框 around it", () => {
    expect(jumpBox(byId("stop-form-9"))).toBe(byId("stop-form-9"));
  });

  // The family page's topic is a 並列區塊 with its heading above the beige block, marked as
  // one: all of it.
  it("is the whole family topic, heading and block together", () => {
    expect(jumpBox(byId("talk-title"))).toBe(titledBy("talk-title"));
  });

  it("is the heading itself when the section it titles is no box", () => {
    expect(jumpBox(byId("share-title"))).toBe(byId("share-title"));
  });

  it("is the 並列區塊 a target is in", () => {
    expect(jumpBox(byId("saved-note"))).toBe(titledBy("saved-title"));
  });

  it("is the target itself when it is in no box", () => {
    expect(jumpBox(byId("question-3"))).toBe(byId("question-3"));
  });
});

// A stand-in window: jsdom does not scroll, so a test sends the scroll events itself. jsdom lays
// nothing out either: every box measures 0 by 0 at the top, in view, unless a test moves it.
function fakeWindow({ hash = "", scrollEnd = false } = {}) {
  const win = Object.assign(new EventTarget(), {
    document: doc,
    location: new URL(ADDRESS + hash),
    innerHeight: 800,
    getComputedStyle: () => ({ position: "static" }),
  });
  if (scrollEnd) win.onscrollend = null;
  return win;
}

const lit = () => [...doc.querySelectorAll(".jump-highlight")];
const click = (name) => [...doc.querySelectorAll("a")].find((a) => a.textContent === name).click();

describe("setUpJumpHighlight", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("lights the box a link on the page jumps to once scrolling pauses, for 3 seconds", () => {
    const win = fakeWindow();
    setUpJumpHighlight(win);
    click("看沒有身障證明時");
    win.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(100);
    win.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(149);
    expect(lit()).toEqual([]);
    vi.advanceTimersByTime(1);
    expect(lit()).toEqual([titledBy("without-certificate")]);
    vi.advanceTimersByTime(2999);
    expect(lit()).toEqual([titledBy("without-certificate")]);
    vi.advanceTimersByTime(1);
    expect(lit()).toEqual([]);
  });

  // A long smooth scroll may pause between frames; where the browser says when scrolling ends,
  // that is what counts.
  it("waits for the scroll to end where the browser tells", () => {
    const win = fakeWindow({ scrollEnd: true });
    setUpJumpHighlight(win);
    click("看沒有身障證明時");
    win.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(1000);
    expect(lit()).toEqual([]);
    win.dispatchEvent(new Event("scrollend"));
    expect(lit()).toEqual([titledBy("without-certificate")]);
  });

  it("lights the box after a short wait when the page is already there", () => {
    setUpJumpHighlight(fakeWindow({ scrollEnd: true }));
    click("看沒有身障證明時");
    vi.advanceTimersByTime(149);
    expect(lit()).toEqual([]);
    vi.advanceTimersByTime(1);
    expect(lit()).toEqual([titledBy("without-certificate")]);
  });

  // In view as #341 counts it: here the phone's tab bar, fixed over the foot of an 800px
  // screen, hides the bottom 80px.
  it("waits until the box is in view above the tab bar", () => {
    const win = fakeWindow();
    win.getComputedStyle = () => ({ position: "fixed" });
    Object.defineProperty(doc.querySelector(".site-nav"), "offsetHeight", { value: 80 });
    const box = titledBy("without-certificate");
    box.getBoundingClientRect = () => ({ top: 600, bottom: 750 });
    setUpJumpHighlight(win);
    click("看沒有身障證明時");
    vi.advanceTimersByTime(1000);
    expect(lit()).toEqual([]);
    box.getBoundingClientRect = () => ({ top: 500, bottom: 650 });
    win.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(150);
    expect(lit()).toEqual([box]);
  });

  // Off and on again, so its fade starts over; the first lighting's 3 seconds no longer count.
  it("lights the box again for 3 seconds when the same link is clicked again", () => {
    setUpJumpHighlight(fakeWindow());
    click("看沒有身障證明時");
    vi.advanceTimersByTime(150 + 2000);
    click("看沒有身障證明時");
    expect(lit()).toEqual([]);
    vi.advanceTimersByTime(150);
    expect(lit()).toEqual([titledBy("without-certificate")]);
    vi.advanceTimersByTime(2999);
    expect(lit()).toEqual([titledBy("without-certificate")]);
    vi.advanceTimersByTime(1);
    expect(lit()).toEqual([]);
  });

  it("takes the light off one box at once when a jump goes to another", () => {
    setUpJumpHighlight(fakeWindow({ hash: "#stop-form-9" }));
    vi.advanceTimersByTime(150);
    click("看沒有身障證明時");
    expect(lit()).toEqual([]);
    vi.advanceTimersByTime(150);
    expect(lit()).toEqual([titledBy("without-certificate")]);
  });

  it("lights the box an address with a # lands on when the page opens", () => {
    setUpJumpHighlight(fakeWindow({ hash: "#stop-form-9" }));
    vi.advanceTimersByTime(150);
    expect(lit()).toEqual([byId("stop-form-9")]);
  });

  it("lights nothing when the page opens at the skip link's landing", () => {
    setUpJumpHighlight(fakeWindow({ hash: "#main-content" }));
    vi.advanceTimersByTime(1000);
    expect(lit()).toEqual([]);
  });

  // A link to another page (or this page with another query, as 修改 is) loads a new page, and
  // that page lights its box.
  it.each(["看再次申請的規定", "修改"])("lights nothing on this page for %s", (name) => {
    setUpJumpHighlight(fakeWindow());
    click(name);
    vi.advanceTimersByTime(1000);
    expect(lit()).toEqual([]);
  });

  // The skip link's landing is used on every page; an error summary's links already mark their
  // question in red.
  it.each(["跳到主要內容", "第 3 題", "有戴的紀錄"])("lights nothing for %s", (name) => {
    setUpJumpHighlight(fakeWindow());
    click(name);
    vi.advanceTimersByTime(1000);
    expect(lit()).toEqual([]);
  });
});
