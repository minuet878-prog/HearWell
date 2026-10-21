// @vitest-environment node
import { readdirSync, readFileSync } from "node:fs";
import { expect, it } from "vitest";

// The Bootstrap components the site kept as named classes (#125). Only those used are defined.
const COMPONENTS = [
  "btn", "btn-lg", "btn-primary", "btn-outline-primary", "btn-outline-light",
  "btn-outline-secondary", "btn-outline-danger", "btn-danger", "btn-link",
  "form-control", "form-control-lg", "form-select", "form-select-lg", "form-label",
  "form-check", "form-check-input", "input-group", "input-group-text",
  "card", "card-body", "table", "alert", "alert-warning", "alert-danger",
  "visually-hidden", "visually-hidden-focusable", "list-unstyled",
];
const BOOTSTRAP_FAMILY = /^(btn(-|$)|form-|input-group|card(-|$)|table(-|$)|alert(-|$)|visually-hidden|list-)/;

function filesIn(dir, pattern) {
  const url = new URL(dir, import.meta.url);
  return readdirSync(url, { recursive: true })
    .filter((name) => pattern.test(name) && !name.includes(".test."))
    .map((name) => readFileSync(new URL(name, url), "utf8"));
}

// Every word a template, React file or Python module could put in a class attribute, the way
// Tailwind scans sources.
const used = new Set(
  [
    ...filesIn("../../screening/templates/", /\.html$/),
    ...filesIn("../../screening/", /^[^/]+\.py$/),
    ...filesIn("./", /\.jsx?$/),
  ].flatMap((text) => text.split(/[^\w-]+/)),
);

const css = readFileSync(new URL("./site.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const defined = new Set(
  [...css.matchAll(/([^{};]+)\{/g)]
    .map(([, prelude]) => prelude.trim())
    .filter((prelude) => !prelude.startsWith("@"))
    .flatMap((selector) => [...selector.matchAll(/\.([a-zA-Z][\w-]*)/g)].map(([, name]) => name)),
);

it("every Bootstrap component the pages use is defined in the site's CSS", () => {
  const missing = COMPONENTS.filter((name) => used.has(name) && !defined.has(name));
  expect(missing).toEqual([]);
});

it("no unused Bootstrap component is carried over", () => {
  const unused = [...defined].filter((name) => BOOTSTRAP_FAMILY.test(name) && !used.has(name));
  expect(unused).toEqual([]);
});
