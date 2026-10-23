import { afterEach, expect, it, vi } from "vitest";

// my_aid.html's subsidy and level questions, as Django renders them (#287).
const FORM = `
  <form>
    <fieldset>
      <input type="radio" name="subsidy" value="" checked>
      <input type="radio" name="subsidy" value="disability">
      <input type="radio" name="subsidy" value="other">
    </fieldset>
    <fieldset data-aid-level>
      <input type="radio" name="level" value="" checked>
      <input type="radio" name="level" value="mid">
    </fieldset>
  </form>`;

afterEach(() => {
  vi.resetModules();
  document.body.innerHTML = "";
});

const level = () => document.querySelector("[data-aid-level]");
const choose = (value) => {
  const radio = document.querySelector(`input[name="subsidy"][value="${value}"]`);
  radio.checked = true;
  radio.dispatchEvent(new Event("change", { bubbles: true }));
};

it("hides the level until 用身障補助 is chosen", async () => {
  document.body.innerHTML = FORM;
  await import("./my-aid.js");
  expect(level().hidden).toBe(true);
  choose("disability");
  expect(level().hidden).toBe(false);
});

it("hides it again when paying otherwise or not answering", async () => {
  document.body.innerHTML = FORM;
  await import("./my-aid.js");
  choose("disability");
  choose("other");
  expect(level().hidden).toBe(true);
  choose("disability");
  choose("");
  expect(level().hidden).toBe(true);
});

it("shows the level on opening when 用身障補助 is saved", async () => {
  document.body.innerHTML = FORM;
  document.querySelector('input[name="subsidy"][value="disability"]').checked = true;
  await import("./my-aid.js");
  expect(level().hidden).toBe(false);
});
