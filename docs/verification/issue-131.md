# #131 Tailwind 遷移收尾驗證（全站比對、文件、驗收）

日期：2026-10-21；分支 `codex/131-tailwind-acceptance`（從 `feat/130-report-pages` 的 `0931dd1` 開出，內容和母分支 `feat/tailwind-migration` 的 `94db418` 相同）。
狀態：自動驗證完成；本人 2026-10-21 回覆「ok」，實際操作驗收通過。子分支合回 `feat/tailwind-migration`；沒有 push、開 PR 或合併回 `main`。

## 範圍與經過

- [#131](https://github.com/minuet878-prog/HearWell/issues/131)、母規格 #119、ADR 0008、ADR 0009。
- Codex 先開工（全站掃描、admin 截圖、文件改寫，未 commit），本人 2026-10-21 請 Claude Code 接手做完。Claude Code 讀過全部改動後保留，改了一處：
  - **拿掉「所有需要登入的頁面加拍未登入版」**：未登入時這些頁面都導到登入頁，拍出來全是同一張登入頁；#122 時本人已確認只對登入前後都看得到的頁面拍兩種。
- 改動：
  - 搜尋測試從「各票列出的模板」改成掃描**全部** Django 模板與 React 檔案。
  - 頁面樣式表的檢查從「整頁沒有 bootstrap 字樣」改成「只載入 `site.css` 和 Google Fonts」。
  - 截圖工具加拍分享連結失效頁、Django admin 登入／首頁／問卷清單（#119 第 13 條）。
  - 程式註解與測試名稱拿掉舊框架的名字（#131 第 3 條）。
  - `AGENTS.md`、`README.md`、`CODING_STANDARDS.md`（新增第 21 條）、無障礙基準線的量測方法改寫成 Tailwind 現況。
- **截圖工具的修正**：admin 登入頁有一個空的 `<footer>`，工具原本只看元素在不在，拍頁尾時等到逾時。改成只拍看得到的頁首／導覽／頁尾；網站自己的頁面這三塊都看得到，張數不變。
- **順手修的格式**：`ruff format --check .`（CI 會跑）在三個檔案失敗。`docs/verification/issue-124.md` 裡的一段 Python 是 #124 留下的；`test_accounts.py`、`test_answering.py` 是 #127、#128 換成較短的 class 名之後沒有重排。不修的話，合併回 `main` 的 PR 會被 CI 擋下。只動排版，意思不變。

## 刻意的差異（本人 2026-10-21 接受）

1. **首頁主標題與說明文字置中**（`f569fd8`，本人在 #130 驗收時另外要求）：首頁 4 張（登入前後 × 390／1024）不同，差異圖上紅色只在標題和說明那兩行，其他像素都沒變。

## #131 驗收條件對照

| 條件 | 證明 |
|---|---|
| 1. 全站截圖比對，每個差異都說明並經本人接受 | 基準在 `origin/main`（`ef638a7`）用暫時的 worktree 拍，本分支再拍，兩邊用同一份截圖工具：**394 張中 390 張逐像素相同，4 張不同都是首頁置中**（上方第 1 項）；字型與基礎字級 0 頁不同。本人 2026-10-21 已接受 |
| 2. e2e、一般測試、前端測試、`ruff check .` 全過 | 見下方「自動驗證」 |
| 3. 全專案搜尋 Bootstrap 只剩 ADR、驗證紀錄、歷史文件 | `git grep -il bootstrap` 共 19 個檔案，全部在 `docs/`：ADR 0008／0009、`docs/verification/` 10 份、`docs/decisions/` 2 份、`docs/specs/` 3 份、`docs/reviews/` 1 份、`docs/accessibility/accessibility_baseline.md`（只剩第 145 行 2026-10-14 量測結果表裡的一列；量測方法段落已改寫）。程式碼、模板、設定檔 0 個 |
| 4. Render 部署腳本不用新增步驟就產生 CSS | `build.sh:11` 本來就跑 `npm run build --prefix frontend`；`frontend/src/bundle.test.js:55` 斷言建置會產出 `site.css` |
| 5. `AGENTS.md` 與 `CODING_STANDARDS.md` 描述 Tailwind 現況與 class 使用規則 | `AGENTS.md:89`（Tailwind CSS v4、Vite 外掛、`frontend/src/site.css` → `screening/static/screening/frontend/site.css`）；`CODING_STANDARDS.md:47` 第 21 條（重複元件與依資料拼接的 class 用有名字的 class，只用一次的排版直接寫 Tailwind，指向 ADR 0008） |
| 6. 驗證紀錄逐條對應 #119 的 13 條 | 下一節 |

## #119 驗收條件對照

| # | 條件 | 證明 |
|---|---|---|
| 1 | 同頁面、寬度、登入狀態的截圖和 `main` 一致，或已列出並經本人接受 | 上方 394 張比對；各票分組比對見 `issue-124.md`～`issue-130.md` |
| 2 | 列印模式截圖一致，頁首、導覽、頁尾、列印按鈕隱藏 | 截圖 `report--report--user--print`、`report--shared-report--anon--print` 相同；`e2e/main_flow.py:1653` 四塊在列印時隱藏（`:1649` 先斷言螢幕上看得到）、`:1658` 沒有陰影、`:1664`～`:1667` 分區與表格不被切開 |
| 3 | 沒有載入 Bootstrap 的 CSS，原始碼沒有 Bootstrap 引用 | `screening/tests/test_pages.py:878` 只載入 `site.css` 和 Google Fonts（由 `:890` 全站各頁、`:933` 失效分享頁、`:938` 同意書頁呼叫）；`:373` 只載入各頁需要的 script；原始碼見上方 #131 第 3 條的搜尋結果 |
| 4 | 第一次載入的 CSS（brotli）不大於遷移前 | `frontend/src/bundle.test.js:57` |
| 5 | 本文、次要文字、分級文字、錯誤文字、結果橫幅的顏色不變 | `e2e/main_flow.py:1533` `test_text_primary_and_error_colours`、`:1550` `test_result_banner_colours`、`:1581` `test_level_badge_colours` |
| 6 | 按鈕、連結卡片、導覽項目、作答選項至少 44×44 | 按鈕 `:1279`；作答選項 `:1604`（高）、`:1605`（寬，本票新增）；連結卡片與導覽項目 `:1624`（本票新增，390／1024 寬、問卷目錄與我的紀錄）。新測試先試驗把兩者高度壓到 20px，10 個子項失敗；還原後通過 |
| 7 | 字級 200%、手機寬度沒有左右捲動、元件不重疊 | `:821` `test_public_and_account_pages_fit_a_phone_at_double_text_size`（`:851` 寬度、`:864` 不重疊）等既有 e2e 照樣通過 |
| 8 | 依分級代碼拼出的徽章與橫幅，四種顏色正確 | `:1550`、`:1581`，四種分級各一個子項 |
| 9 | 沒有 JavaScript 完成問卷，作答頁和結果頁一樣 | 截圖四份問卷的 `--nojs` 作答頁與各結果頁相同；`:101` `test_adult_completes_hhia_s_without_javascript` |
| 10 | e2e、一般測試、前端測試全過 | 見下方「自動驗證」 |
| 11 | Render 建置不用新增步驟就產生 CSS | 同 #131 第 4 條 |
| 12 | 合併時 `AGENTS.md` 寫 Tailwind，規範有 class 使用規則 | 同 #131 第 5 條 |
| 13 | Django admin 樣子和遷移前一樣 | 截圖 admin 登入、首頁、問卷清單 × 390／1024 相同（本票新增） |

截圖沒拍到、靠各票逐條核對數值確認的：表單錯誤狀態（#119 使用者故事 14）、React 作答頁的「已經送出過」「要接著答嗎」等狀態、1200px 以上的字級、圖表的錯誤文字、admin 其他頁面。

## 自動驗證

| 檢查 | 結果 |
|---|---|
| Django 全套 | 646 個通過 |
| 前端 | 13 檔、190 個通過 |
| e2e `e2e.main_flow` 全套 | 44 個通過（含本票新增 1 個） |
| `ruff check .`、`ruff format --check .` | 通過（格式修正見上方） |
| `npm run build --prefix frontend` | 通過 |
| 全站截圖 | 兩邊各 394 張，比對見上方 |

截圖工具的 8765 埠被本機另一個專案佔用，沒有停它；兩邊都暫時改成 8766 拍，拍完已還原。

## 自審

`/mattpocock-skills:code-review`，基準 `feat/tailwind-migration`，Standards 與 Spec 各由一個子代理審查。

- Standards：0 項硬性違規；判斷題 7 項。
- Spec：0 項要修；可考慮 6 項。

| 發現 | 處理 |
|---|---|
| 註解拿掉舊框架名字後只寫「original blue」，看不出指什麼（兩邊都提） | 已改：寫出 `#0d6efd`、`rgba(49, 132, 253, 0.5)`，並註明是遷移前框架的值 |
| 搜尋測試失敗時印出本機完整路徑 | 已改：印專案內的相對路徑；試驗放一個含 `d-flex` 的檔案，測試會列出它（已刪除） |
| admin 測試帳號設了用不到的密碼 | 已拿掉 |
| 觸控尺寸測試用連結文字當子項名稱，純圖示連結會出錯 | 已改用連結網址 |
| 作答選項只量高度（#119 第 6 條） | 已補寬度斷言 |
| 改了 #124 的驗證紀錄（判斷為無關改動） | 不還原：CI 的 `ruff format --check .` 會擋，見上方 |
| 樣式表檢查寫死 Google Fonts 網址，和 `layout.html` 重複 | 不改：測試要寫出預期值；以後改字型要改兩處 |
| 失效分享頁、同意書頁不再檢查「整頁沒有 bootstrap 字樣」 | 不改：頁面從沒載入過舊框架的 JS，樣式表已經逐一比對；把這個字寫回測試又違反 #131 第 3 條 |
| 原始碼沒有 Bootstrap 引用沒有自動測試 | 用上方 `git grep` 的結果當證據 |
| 搜尋測試一行一行比，跨行的 `class` 會漏；`forms.py` 用程式加的 class 掃不到 | 不改：沒有跨行寫法；`forms.py` 只加 `form-control`、`form-select`、`choice-group` 等有名字的 class |
| `docs/roadmap.md` 還提到已刪除的 `styles.css` | 收尾更新 roadmap 時處理（`.text-success／warning／danger` 已不存在） |

不需交叉審查：只改測試、文件與樣式註解，沒有修改計分、分級、門檻、資料 migration 或權限。

## 本人實際操作（2026-10-21 通過）

- [x] 接受上方「刻意的差異」第 1 項（首頁置中）。
- [x] 看過全站比對報告（`e2e-artifacts/shots/131-diff/report.md`，不進版控）。
- [x] 讀過 `AGENTS.md` 專案概要與 `CODING_STANDARDS.md` 第 21 條。
- [x] 抽看幾頁（例如首頁、作答、聽力報告列印預覽、Django admin），畫面和正式站一樣。
