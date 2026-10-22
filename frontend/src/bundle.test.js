// @vitest-environment node
import { brotliCompressSync } from "node:zlib";
import { fileURLToPath } from "node:url";

import { build } from "vite";
import { expect, it } from "vitest";

const LIMIT = 80 * 1024;
// Before the migration every page loaded the framework CSS (22,970 bytes) and the old
// styles.css (5,489 bytes), measured brotli in the same way as below (#124).
const CSS_LIMIT = 22_970 + 5_489;
// Until #181 every page also loaded Google Fonts' Noto Sans TC stylesheet, 20,405 bytes measured
// the same way; its @font-face rules now ship inside site.css (ADR 0014).
const FONT_CSS_LIMIT = 20_405;
const FONT_FACE = /@font-face\s*\{[^}]*\}/g;

async function buildOutput() {
  const root = fileURLToPath(new URL("..", import.meta.url));
  // Vitest sets NODE_ENV=test, which would bundle React's larger development build.
  const nodeEnv = process.env.NODE_ENV;
  process.env.NODE_ENV = "production";
  const result = await build({ root, logLevel: "silent", build: { write: false } }).finally(() => {
    process.env.NODE_ENV = nodeEnv;
  });
  return [result].flat().flatMap((r) => r.output);
}

async function entryDownload(name) {
  const chunks = (await buildOutput()).filter((o) => o.type === "chunk");
  const byFile = Object.fromEntries(chunks.map((c) => [c.fileName, c]));

  // The entry plus everything it imports statically is what the browser downloads.
  const seen = new Set();
  const visit = (chunk) => {
    if (seen.has(chunk)) return;
    seen.add(chunk);
    chunk.imports.forEach((file) => visit(byFile[file]));
  };
  visit(chunks.find((c) => c.isEntry && c.name === name));

  return {
    modules: [...seen].flatMap((c) => c.moduleIds),
    size: [...seen].reduce((sum, c) => sum + brotliCompressSync(c.code).length, 0),
  };
}

// The audiogram pages draw their own SVG; neither should pull in Recharts.
for (const name of ["answer", "audiogram-input", "audiogram-view"]) {
  it(`the ${name} page loads no chart library and stays under 80 KB (brotli)`, async () => {
    const { modules, size } = await entryDownload(name);
    expect(modules.some((id) => id.includes("recharts"))).toBe(false);
    expect(size).toBeLessThanOrEqual(LIMIT);
  }, 60_000);
}

// Every page loads the site's CSS on its first visit: its own rules cost no more than the
// pre-migration CSS, and the font's rules no more than the Google Fonts stylesheet they replace.
it("the site's CSS is built and costs no more than the CSS it replaced (brotli)", async () => {
  const css = (await buildOutput()).filter((o) => o.fileName.endsWith(".css"));
  expect(css.map((o) => o.fileName)).toContain("site.css");
  const source = css.map((o) => o.source).join("\n");
  const brotli = (text) => brotliCompressSync(text).length;
  expect(brotli(source.replace(FONT_FACE, ""))).toBeLessThanOrEqual(CSS_LIMIT);
  expect(brotli((source.match(FONT_FACE) ?? []).join("\n"))).toBeLessThanOrEqual(FONT_CSS_LIMIT);
}, 60_000);
