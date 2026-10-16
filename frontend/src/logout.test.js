import { afterEach, expect, it, vi } from "vitest";

import { DRAFT_PREFIX } from "./draft.js";

afterEach(() => {
  vi.resetModules();
  localStorage.clear();
  document.body.innerHTML = "";
});

it("logging out clears the unfinished answers", async () => {
  document.body.innerHTML = '<form id="logout-form" action="/logout" method="post"></form>';
  localStorage.setItem(`${DRAFT_PREFIX}1`, "{}");
  localStorage.setItem("something-else", "x");
  await import("./logout.js");
  document.getElementById("logout-form").dispatchEvent(new Event("submit"));
  expect(localStorage.getItem(`${DRAFT_PREFIX}1`)).toBeNull();
  expect(localStorage.getItem("something-else")).toBe("x");
});

it("deleting the account clears the unfinished answers too", async () => {
  document.body.innerHTML = '<form id="delete-account-form" method="post"></form>';
  localStorage.setItem(`${DRAFT_PREFIX}1`, "{}");
  await import("./logout.js");
  document.getElementById("delete-account-form").dispatchEvent(new Event("submit"));
  expect(localStorage.getItem(`${DRAFT_PREFIX}1`)).toBeNull();
});
