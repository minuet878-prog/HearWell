"""Compare two screenshot captures from e2e/screenshots.py pixel by pixel (#122, #119).

    py313/bin/python e2e/compare_shots.py e2e-artifacts/shots/main e2e-artifacts/shots/branch
    py313/bin/python e2e/compare_shots.py <base> <new> --group answering

Writes report.md and a diff image per differing screenshot into <new>-diff/, and exits 1 if
anything differs. Any changed pixel counts: two captures of one commit match exactly, so even
a slightly different grey shows up and a person decides whether it is acceptable. Screenshots
of different sizes are compared over the larger size, the missing part counting as changed.
The font and root font size in each capture's styles.json are compared too.
Uses the Chromium that Playwright already installed, so no image library is needed.
"""

import argparse
import base64
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

COMPARE_JS = """
async ([a, b]) => {
  const load = (src) => new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = src;
  });
  const [first, second] = await Promise.all([load(a), load(b)]);
  const width = Math.max(first.width, second.width);
  const height = Math.max(first.height, second.height);
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
    const same = [0, 1, 2, 3].every((c) => before[i + c] === after[i + c]);
    if (!same) {
      count += 1;
      diff.data.set([255, 0, 0, 255], i);
    } else {
      // The unchanged page stays faintly visible behind the red pixels.
      const grey = 255 - (255 - (before[i] + before[i + 1] + before[i + 2]) / 3) * 0.2;
      diff.data.set([grey, grey, grey, 255], i);
    }
  }
  const sizes = [[first.width, first.height], [second.width, second.height]];
  if (count === 0) return { count, sizes };
  outContext.putImageData(diff, 0, 0);
  const bytes = new Uint8Array(await (await out.convertToBlob()).arrayBuffer());
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return { count, sizes, diff: btoa(binary) };
}
"""


def data_url(path):
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def compare_styles(base, new, prefix):
    rows = []
    styles_base = json.loads((base / "styles.json").read_text(encoding="utf-8"))
    styles_new = json.loads((new / "styles.json").read_text(encoding="utf-8"))
    for name in sorted(set(styles_base) & set(styles_new)):
        if name.startswith(prefix) and styles_base[name] != styles_new[name]:
            rows.append(f"| {name} | 樣式不同：{styles_base[name]} → {styles_new[name]} |")
    return rows


def compare(base, new, group):
    prefix = f"{group}--" if group else ""
    out = new.with_name(f"{new.name}-diff")
    out.mkdir(exist_ok=True)
    names_base = {p.name for p in base.glob(f"{prefix}*.png")}
    names_new = {p.name for p in new.glob(f"{prefix}*.png")}
    rows = [f"| {n} | 只在基準 |" for n in sorted(names_base - names_new)]
    rows += [f"| {n} | 只在新的 |" for n in sorted(names_new - names_base)]
    same = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        for name in sorted(names_base & names_new):
            result = page.evaluate(COMPARE_JS, [data_url(base / name), data_url(new / name)])
            if result["count"] == 0:
                same += 1
                continue
            (out / name).write_bytes(base64.b64decode(result["diff"]))
            (bw, bh), (nw, nh) = result["sizes"]
            size = f"，尺寸 {bw}x{bh} → {nw}x{nh}" if (bw, bh) != (nw, nh) else ""
            rows.append(f"| {name} | {result['count']} 個像素不同{size}（[差異圖]({name})） |")
        browser.close()
    styles = compare_styles(base, new, prefix)
    rows += styles
    total = len(names_base | names_new)
    lines = [
        f"# 截圖比對：{base} → {new}",
        "",
        f"共 {total} 張，{same} 張畫面相同，{total - same} 張畫面有差異；"
        f"{len(styles)} 頁的字型或基礎字級不同。",
    ]
    if rows:
        lines += ["", "| 截圖 | 差異 |", "|---|---|", *rows]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return not rows


def main():
    parser = argparse.ArgumentParser(description="Compare two screenshot captures.")
    parser.add_argument("base", type=Path)
    parser.add_argument("new", type=Path)
    parser.add_argument("--group", default="", help="public, answering, history, report, chrome")
    args = parser.parse_args()
    for folder in (args.base, args.new):
        if not (folder / "styles.json").is_file():
            parser.error(f"{folder} is not a capture from e2e/screenshots.py")
    sys.exit(0 if compare(args.base, args.new, args.group) else 1)


if __name__ == "__main__":
    main()
