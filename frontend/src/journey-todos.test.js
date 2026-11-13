import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SAVED_FOR, tickInPlace } from "./journey-todos.js";
import { setUpPageLoading } from "./page-loading.js";

// #481 (spec #478): a 手動待辦's row is a form's button read as a checkbox, as
// journey_todos.html writes it; here it saves without leaving the page and says ✓ 已儲存.

function row(key, ticked) {
  return `<li class="todo todo-manual${ticked ? " is-done" : ""}" data-todo="${key}" id="todo-${key}">
    <form class="todo-form" method="post" action="/journey_todo_tick" data-todo-tick>
      <input type="hidden" name="csrfmiddlewaretoken" value="token">
      <input type="hidden" name="todo" value="${key}">
      <input type="hidden" name="ticked" value="${ticked ? "0" : "1"}">
      <input type="hidden" name="next" value="/">
      <button type="submit" class="todo-button" role="checkbox" aria-checked="${ticked}">
        <span class="todo-box" aria-hidden="true">${ticked ? "<svg></svg>" : ""}</span>
        <span class="todo-text">預約開九號表</span>
      </button>
    </form>
  </li>`;
}

const replies = [];

function answer(body, init = { status: 200 }) {
  replies.push(new Response(JSON.stringify(body), init));
}

beforeEach(() => {
  document.body.innerHTML = `<ul class="todo-list">${row("form-9-book", false)}${row("form-9-other", true)}</ul>`;
  replies.length = 0;
  window.fetch = vi.fn(async () => replies.shift());
  HTMLFormElement.prototype.submit = vi.fn();
  tickInPlace(document, window);
});

afterEach(() => {
  vi.useRealTimers();
});

const item = (key) => document.querySelector(`[data-todo="${key}"]`);
const button = (key) => item(key).querySelector("button");
const saved = () => [...document.querySelectorAll(".todo-saved")];

async function press(key) {
  button(key).click();
  // The reply, then its JSON.
  await vi.waitFor(() => expect(window.fetch).toHaveBeenCalled());
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("tickInPlace", () => {
  it("sends the row's form asking for JSON, the page staying", async () => {
    answer({ ticked: true });
    await press("form-9-book");
    const [url, init] = window.fetch.mock.calls[0];
    expect(url).toBe("http://localhost:3000/journey_todo_tick");
    expect(init.method).toBe("POST");
    expect(init.headers.Accept).toBe("application/json");
    expect(Object.fromEntries(init.body)).toMatchObject({
      csrfmiddlewaretoken: "token",
      todo: "form-9-book",
      ticked: "1",
    });
    expect(HTMLFormElement.prototype.submit).not.toHaveBeenCalled();
  });

  it("ticks the row and says ✓ 已儲存 beside it", async () => {
    answer({ ticked: true });
    await press("form-9-book");
    expect(button("form-9-book").getAttribute("aria-checked")).toBe("true");
    expect(item("form-9-book").classList.contains("is-done")).toBe(true);
    expect(item("form-9-book").querySelector(".todo-box svg")).not.toBeNull();
    expect(item("form-9-book").querySelector('[name="ticked"]').value).toBe("0");
    expect(saved().map((s) => s.textContent)).toEqual(["✓ 已儲存"]);
    expect(saved()[0].closest("li")).toBe(item("form-9-book"));
    expect(saved()[0].getAttribute("aria-hidden")).toBe("true");
  });

  it("unticks a ticked row, saying ✓ 已儲存 too (the owner's D4)", async () => {
    answer({ ticked: false });
    await press("form-9-other");
    expect(button("form-9-other").getAttribute("aria-checked")).toBe("false");
    expect(item("form-9-other").classList.contains("is-done")).toBe(false);
    expect(item("form-9-other").querySelector(".todo-box svg")).toBeNull();
    expect(item("form-9-other").querySelector('[name="ticked"]').value).toBe("1");
    expect(saved()[0].closest("li")).toBe(item("form-9-other"));
  });

  it("draws the tick once only on the row just ticked", async () => {
    answer({ ticked: true });
    await press("form-9-book");
    expect(item("form-9-book").querySelector(".todo-box svg").classList).toContain("todo-tick");
    expect(item("form-9-other").querySelector(".todo-box svg").classList).not.toContain(
      "todo-tick",
    );
  });

  it("keeps ✓ 已儲存 for a while, then takes it away", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    answer({ ticked: true });
    button("form-9-book").click();
    // Not vi.waitFor, which would run the faked clock on while it waits.
    for (let i = 0; i < 100 && !saved().length; i++) await Promise.resolve();
    vi.advanceTimersByTime(SAVED_FOR - 1);
    expect(saved()).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(saved()).toHaveLength(0);
  });

  it("shows one ✓ 已儲存 at a time, beside the row pressed last", async () => {
    answer({ ticked: true });
    await press("form-9-book");
    answer({ ticked: false });
    await press("form-9-other");
    expect(saved()).toHaveLength(1);
    expect(saved()[0].closest("li")).toBe(item("form-9-other"));
  });

  it("sends the form the plain way when the reply is not a save", async () => {
    // Signed out meanwhile, the server sends the login page (a redirect); or it failed.
    replies.push(new Response(null, { status: 302 }));
    await press("form-9-book");
    expect(HTMLFormElement.prototype.submit).toHaveBeenCalledTimes(1);
    expect(button("form-9-book").getAttribute("aria-checked")).toBe("false");
    expect(saved()).toHaveLength(0);
  });

  it("is no page to wait for: page-loading.js, set up first, leaves the row alone", async () => {
    // e2e found it: page-loading.js put 送出中… in the button in place of the box, which then
    // was not there to tick, and the row was sent again the plain way, unticking it.
    document.body.innerHTML = `<p id="page-loading-status"></p><main><ul>${row("form-9-book", false)}</ul></main>`;
    const fresh = document.implementation.createHTMLDocument("");
    fresh.body.innerHTML = document.body.innerHTML;
    const win = { document: fresh, fetch: window.fetch, setTimeout, clearTimeout, addEventListener() {} };
    setUpPageLoading(win);
    tickInPlace(fresh, win);
    answer({ ticked: true });
    fresh.querySelector("button").click();
    await vi.waitFor(() => expect(fresh.querySelector(".todo-saved")).not.toBeNull());
    expect(fresh.querySelector("button").getAttribute("aria-checked")).toBe("true");
    expect(fresh.querySelector(".spinner")).toBeNull();
    expect(fresh.getElementById("page-loading-status").textContent).toBe("");
    expect(HTMLFormElement.prototype.submit).not.toHaveBeenCalled();
  });

  it("sends the form the plain way when the network fails", async () => {
    window.fetch = vi.fn(async () => {
      throw new TypeError("offline");
    });
    button("form-9-book").click();
    await vi.waitFor(() => expect(HTMLFormElement.prototype.submit).toHaveBeenCalledTimes(1));
  });
});
