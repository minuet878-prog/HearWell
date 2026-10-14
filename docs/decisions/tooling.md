# 開發工具與流程

← [回到索引](README.md)

---

## 2026-08-31 Python 巢狀 class 的作用域陷阱

**情境**
把 `Question.category` 從自由字串改成 `TextChoices` + `CheckConstraint` 時，把
`Category` 這個 `TextChoices` 定義在 `Question` 內部（跟 `category` 欄位同一層），
結果 `Meta.constraints` 裡引用 `Category.values` 時噴 `NameError`。

**除錯過程**
一開始以為只是 linter 誤判（`makemigrations` 曾經一度沒報錯，但後來確認是沒有真的
存檔跑到新版本）。改成 `Question.Category.values` 之後，又噴另一個 `NameError`——
這次是 `Question` 這個名字本身在自己的 class body 內部還不存在（class 定義要整段
body 執行完，才會把結果綁定到 class 名稱上）。

**決定**
把 `Category` 搬到檔案最頂層（跟 `Question` 平行，不再巢狀在裡面）。

**理由**
Python 的 class body 是「由上到下依序執行」的程式碼區塊，巢狀 class 之間互不相通
（不會像函式閉包那樣自動借用外層變數），只有「模組層級（檔案最上層）」的名字，才能
被任何巢狀深度的程式碼直接看到。`Category` 本身不對應任何資料庫結構（只是 Python
層面定義選項的工具），搬動它的位置不影響 migration，`makemigrations` 也證實了這點
（搬動後沒有產生新的 schema 變化）。

**代價 / 取捨**
- 無明顯代價，純粹是程式碼組織方式的調整。附帶好處：`Category` 放在模組頂層後，
  之後如果 `forms.py` 或別的檔案需要用到這個選項定義，可以直接 import，不用透過
  `Question.Category` 這種比較繞的路徑。

---

## 2026-09-23 ruff 排除 migrations

- migrations 是 Django 自動產生的，31 個 E501 全在裡面，真正的錯誤會被淹沒，linter 等於沒在用。
- 用 `extend-exclude` 不用 `exclude`：`exclude` 會蓋掉 ruff 內建的排除清單（`.venv`、`.git` 那些），`extend-exclude` 是往上加。
- 驗證要做兩個方向：migration 的錯誤不見了，**而且**在 screening 故意加一行沒用到的 import 還抓得到。只驗證前者的話，把全部都排除掉也會「通過」。

---

## 2026-09-23 Git 流程：main 分岔

- 在本機 main 直接 commit 了 CLAUDE.md 沒 push，同時 PR 在 GitHub 上合併，`git pull` 就分岔了。
- 用 `git pull --rebase` 解決：commit 還沒 push 過，rebase 是安全的。已經 push 的 commit 不要 rebase。
- 設了 `pull.ff only`：main 只該透過 PR 前進，一旦分岔就是流程出錯，要讓 Git 擋下來。
- 教訓：連改文件都要開分支。

---

## 2026-09-23 ruff 擴充規則集（B / DJ / TID / RUF）

- 一次加一組規則、每組跑一次 check，才分得出哪個錯是哪組抓的。DJ、TID 沒抓到東西，B 抓 2 個、RUF 抓 22 個。
- **RUF001 用白名單不用全域忽略**：中文文案的全形「，」「？」是刻意的，但全域忽略會連西里爾字母、零寬字元這些真正危險的一起放過。`allowed-confusables` 只放行這兩個，以後用到新的全形符號再加。
- **RUF012 list 改 tuple，接受多一個 migration**：`ordering` 從 list 改 tuple，Django 會判定成設定變更，生出 0011。`sqlmigrate` 確認是 no-op。選擇接受它，不用 `noqa`，因為 `noqa` 會在程式碼裡留下越積越多的例外。
- **B905 GET 和 POST 分開處理**：GET 的長度由 `questions` 決定，`strict=True` 是保險。POST 的長度來自使用者，而且 zip 在驗證之前跑，加 `strict` 會讓竄改的送出變成 500。POST 先 `noqa` ＋ `TODO(phase1-7)`，等驗證搬到 form 層再改。
- 坑：`# noqa` 要寫在出錯那一行的行尾，寫在上一行沒效。
