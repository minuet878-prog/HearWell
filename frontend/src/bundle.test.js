// @vitest-environment node
import { brotliCompressSync } from "node:zlib";
import { fileURLToPath } from "node:url";

import { build } from "vite";
import { expect, it } from "vitest";

const LIMIT = 80 * 1024;

it("the answer page loads no chart library and stays under 80 KB (brotli)", async () => {
  const root = fileURLToPath(new URL("..", import.meta.url));
  // Vitest sets NODE_ENV=test, which would bundle React's larger development build.
  const nodeEnv = process.env.NODE_ENV;
  process.env.NODE_ENV = "production";
  const result = await build({ root, logLevel: "silent", build: { write: false } }).finally(() => {
    process.env.NODE_ENV = nodeEnv;
  });
  const chunks = [result].flat().flatMap((r) => r.output).filter((o) => o.type === "chunk");
  const byFile = Object.fromEntries(chunks.map((c) => [c.fileName, c]));

  // The entry plus everything it imports statically is what the browser downloads.
  const seen = new Set();
  const visit = (chunk) => {
    if (seen.has(chunk)) return;
    seen.add(chunk);
    chunk.imports.forEach((file) => visit(byFile[file]));
  };
  visit(chunks.find((c) => c.isEntry && c.name === "answer"));

  const modules = [...seen].flatMap((c) => c.moduleIds);
  expect(modules.some((id) => id.includes("recharts"))).toBe(false);
  const size = [...seen].reduce((sum, c) => sum + brotliCompressSync(c.code).length, 0);
  expect(size).toBeLessThanOrEqual(LIMIT);
}, 60_000);
