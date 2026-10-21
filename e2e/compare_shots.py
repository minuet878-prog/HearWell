"""Compare two screenshot captures from e2e/screenshots.py pixel by pixel (#122, #119).

    py313/bin/python e2e/compare_shots.py e2e-artifacts/shots/main e2e-artifacts/shots/branch

Writes report.md and a diff image per differing screenshot into <new>-diff/, and exits 1 if
anything differs. A pixel counts as different when a colour channel moves by more than
--tolerance (anti-aliasing stays below it); a screenshot differs when more than --pixels do.
--only takes a filename prefix, e.g. "answering--" or "chrome--", to compare one group.
Uses the Chromium that Playwright already installed, so no image library is needed.
"""

import argparse
import base64
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

COMPARE_JS = """
async ([a, b, tolerance]) => {
  const load = (src) => new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = src;
  });
  const [first, second] = await Promise.all([load(a), load(b)]);
  if (first.width !== second.width || first.height !== second.height) {
    return { size: [[first.width, first.height], [second.width, second.height]] };
  }
  const { width, height } = first;
  const pixels = (image) => {
    const canvas = new OffscreenCanvas(width, height);
    const context = canvas.getContext("2d");
    context.drawImage(image, 0, 0);
    return context.getImageData(0, 0, width, height).data;
  };
  const before = pixels(first);
  const after = pixels(second);
  const out = new OffscreenCanvas(width, height);
  const outContext = out.getContext("2d");
  const diff = outContext.createImageData(width, height);
  let count = 0;
  for (let i = 0; i < before.length; i += 4) {
    const delta = Math.max(
      Math.abs(before[i] - after[i]),
      Math.abs(before[i + 1] - after[i + 1]),
      Math.abs(before[i + 2] - after[i + 2]),
    );
    if (delta > tolerance) {
      count += 1;
      diff.data.set([255, 0, 0, 255], i);
    } else {
      // The unchanged page stays faintly visible behind the red pixels.
      const grey = 255 - (255 - (before[i] + before[i + 1] + before[i + 2]) / 3) * 0.2;
      diff.data.set([grey, grey, grey, 255], i);
    }
  }
  if (count === 0) return { count };
  outContext.putImageData(diff, 0, 0);
  const bytes = new Uint8Array(await (await out.convertToBlob()).arrayBuffer());
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return { count, diff: btoa(binary) };
}
"""


def data_url(path):
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def compare(base, new, tolerance, pixels, only):
    out = new.with_name(f"{new.name}-diff")
    out.mkdir(exist_ok=True)
    names_base = {p.name for p in base.glob(f"{only}*.png")}
    names_new = {p.name for p in new.glob(f"{only}*.png")}
    rows = [f"| {n} | 只在基準 |" for n in sorted(names_base - names_new)]
    rows += [f"| {n} | 只在新的 |" for n in sorted(names_new - names_base)]
    same = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        for name in sorted(names_base & names_new):
            result = page.evaluate(
                COMPARE_JS, [data_url(base / name), data_url(new / name), tolerance]
            )
            if "size" in result:
                (bw, bh), (nw, nh) = result["size"]
                rows.append(f"| {name} | 尺寸不同：{bw}x{bh} → {nw}x{nh} |")
            elif result["count"] > pixels:
                (out / name).write_bytes(base64.b64decode(result["diff"]))
                rows.append(f"| {name} | {result['count']} 個像素不同（[差異圖]({name})） |")
            else:
                same += 1
        browser.close()
    total = len(names_base | names_new)
    lines = [
        f"# 截圖比對：{base} → {new}",
        "",
        f"共 {total} 張，{same} 張相同，{total - same} 張有差異"
        f"（顏色容差 {tolerance}、像素門檻 {pixels}）。",
    ]
    if rows:
        lines += ["", "| 截圖 | 差異 |", "|---|---|", *rows]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return not rows


def main():
    parser = argparse.ArgumentParser(description="Compare two screenshot captures pixel by pixel.")
    parser.add_argument("base", type=Path)
    parser.add_argument("new", type=Path)
    parser.add_argument("--tolerance", type=int, default=16)
    parser.add_argument("--pixels", type=int, default=20)
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    for folder in (args.base, args.new):
        if not folder.is_dir():
            parser.error(f"{folder} is not a folder of screenshots")
    sys.exit(0 if compare(args.base, args.new, args.tolerance, args.pixels, args.only) else 1)


if __name__ == "__main__":
    main()
