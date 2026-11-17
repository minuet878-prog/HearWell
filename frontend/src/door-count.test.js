import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { countDoorPresses } from "./door-count.js";

// Spec #655 (#673) acceptance 23: a press of a door on the signed-out home adds one to its own
// column of the 訪客月計數, sent so it still goes as the page moves on.
beforeEach(() => {
  window.fetch = vi.fn(async () => new Response(null, { status: 204 }));
  document.body.innerHTML = `
    <a href="#self" data-door="door_self">我想了解自己的聽力</a>
    <a href="#family" data-door="door_family">我擔心家人的聽力</a>
    <a href="#login">我已經有帳號，登入</a>`;
  countDoorPresses();
});

afterEach(() => {
  document.body.innerHTML = "";
});

const sent = () =>
  window.fetch.mock.calls.map(([url, init]) => [url, init.method, JSON.parse(init.body), init.keepalive]);

describe("countDoorPresses", () => {
  it("sends the pressed door's kind, and only once per press", () => {
    document.querySelector("[data-door=door_family]").click();
    expect(sent()).toEqual([["/api/guest-counts/", "POST", { kind: "door_family" }, true]]);
    document.querySelector("[data-door=door_self]").click();
    expect(sent()[1][2]).toEqual({ kind: "door_self" });
  });

  it("sends nothing for the page's other links, or before a press", () => {
    expect(window.fetch).not.toHaveBeenCalled();
    document.querySelector("[href='#login']").click();
    expect(window.fetch).not.toHaveBeenCalled();
  });
});
