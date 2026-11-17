# ship_docs.py 認不得中文檔名

日期：2026-11-17。分支：`fix/ship-docs-unicode-paths`。

## 問題與原因

PR #729 只加 `docs/` 底下的檔案，`scripts/ship_docs.py` 卻回「有 docs/、GLOSSARY.md 以外的檔案」，列出三張設計圖：

```text
"docs/design/\345\256\232\347\250\277\357\275\234\351\246\226\351\240\201@1x.png"
```

`git diff --name-only` 預設把非 ASCII 的檔名加上引號、轉成八進位（`core.quotePath`）。開頭變成 `"docs/`，不是 `docs/`，所以 `is_docs` 判斷失敗。

## 修正

列檔名改用 `git diff --name-only -z`：檔名照原樣、用 `\0` 分隔，中文、空白、引號都不會被改寫。抽成 `changed_paths()` 讓測試可以直接呼叫。

## 測試

- 新增 `screening/tests/test_ship_docs.py`，在暫存資料夾開一個 git repo：
  - `docs/design/定稿首頁.png` 算在 `docs/` 裡。舊寫法下這條失敗，拿到的是 `'"docs/design/\\345\\256...png"'`；修正後通過。
  - `README.md` 照樣被擋下。
- 後端 3159 個測試通過（`--parallel`）；`ruff check .`、`ruff format --check .` 通過。
- 只改部署輔助腳本，沒碰計分、門檻、migration、權限，不需交叉審查。
