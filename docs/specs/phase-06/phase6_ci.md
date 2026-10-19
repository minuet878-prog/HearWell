# Phase 6 規格：CI（自動檢查）

- **狀態**：已完成
- **分支**：`ci/github-actions`
- **擬稿**：AI　　**確認人**：本人　　**確認日期**：2026-10-16

> 給 AI 的說明：本規格狀態為「已確認」之前，不得開始實作。
> 規格沒寫到、而且會影響行為的地方，先停下來問，不要自行決定。

---

## 1. 目標

開 PR 的時候，GitHub 自動跑完本機會跑的檢查，結果直接顯示在 PR 頁面上。
壞掉的程式在合併前就被擋下來，不靠「記得在本機跑過」。之後 Phase 6 的每一項修正都有這層保護。

## 2. 範圍

### 要做
- 用 GitHub Actions（GitHub 內建的 CI 服務；公開 repo 免費）
- 檢查四件事（任一件失敗，整次檢查就算失敗）：
  1. Django 測試（`config.test_settings`），資料庫用 PostgreSQL 18（跟正式環境同版本）
  2. `ruff check`（只檢查、不自動修正）
  3. 前端測試
  4. 前端建置（`npm run build`）：先在 CI 抓到，不要等到 Render 部署才失敗
- Python、Node 版本讀 repo 裡的 `.python-version`、`.node-version`，不另外寫一份
- 套件只用 lock 檔裝（`requirements-dev.txt`、`package-lock.json`）

### 不做
- `ruff format` 排版檢查（目前有 5 個檔案不符合，專案沒有要求排版）
- 自動部署、自動合併、自動修正後推回分支
- 在 CI 跑 `check --deploy`（需要正式環境的環境變數；部署時 `build.sh` 已經在跑）
- 測試覆蓋率報告、徽章（badge）、通知到 email 以外的地方
- 多個 Python／Node 版本同時測（只測正式環境用的那一版）
- 改動任何既有程式碼或測試；`ruff` 搬到 `requirements-dev.txt` 是 Phase 6 下一項，這次不動

## 3. 必須遵守的規則

- 一律遵守 CLAUDE.md「不可違反的規則」。
- 本 phase 特別注意：
  - CI 用的資料庫是 CI 裡臨時建立的空資料庫，密碼是寫死的假值，不是 `.env` 的任何東西，也不連 Neon
  - CI 設定檔裡不能出現任何真實的密碼、金鑰、連線字串
  - CI 只讀程式碼、不寫回 repo（權限設成唯讀）

## 4. 行為描述

### 4.1 什麼時候跑

| 項目 | 內容 |
|---|---|
| 觸發時機 | 開 PR、PR 有新的 push、合併進 `main` 之後。沒開 PR 的分支 push 不跑 |
| 結果顯示在哪 | PR 頁面底下的檢查區（綠勾／紅叉），點進去看得到哪一步失敗、錯誤訊息 |
| 失敗時 | PR 不能合併（GitHub 分支保護，本人設定）；`main` 上沒過就不部署（Render「CI 通過後才部署」，本人設定） |
| 同一個 PR 連續推兩次 | 取消還沒跑完的舊的，只跑最新的 |

## 5. 驗收條件

- [x] 1. 假設 PR 的程式碼全部正常，當 CI 跑完，則 PR 頁面顯示通過，四項檢查都有跑（點進去看得到四段結果）。
- [x] 2. 假設有一個 Django 測試失敗，當 CI 跑完，則整次檢查顯示失敗，紀錄裡看得到失敗的測試名稱。
- [x] 3. 假設有一行 `ruff` 會抓到的錯（例如沒用到的 import），當 CI 跑完，則顯示失敗，紀錄裡看得到檔名和行號。
- [x] 4. 假設有一個前端測試失敗，當 CI 跑完，則顯示失敗。
- [x] 5. 假設前端程式建置不過（例如 import 一個不存在的檔案），當 CI 跑完，則顯示失敗。
- [x] 6. 假設 Django 測試裡有用到 PostgreSQL 才有的行為，當 CI 跑完，則確實是在 PostgreSQL 18 上跑（紀錄裡看得到資料庫版本），不是 SQLite。
- [x] 7. 假設 CI 設定檔，當檢查內容，則沒有任何真實的密碼或連線字串；CI 的權限是唯讀。
- [x] 8. 假設 `.python-version` 是 3.13.15、`.node-version` 是 24.21.0，當 CI 跑，則用的就是這兩個版本（紀錄裡看得到）。
- [x] 9. 假設一條分支有 push 但沒有開 PR，當 push，則 CI 不跑；開 PR 後才跑；PR 合併進 `main` 後，`main` 上也跑一次。
  - 前半（沒開 PR 不跑、開 PR 才跑）2026-10-16 確認；後半：PR #40 合併後，`main` 的 `b39da2d` 跑了一次（05:00:36–05:01:34 UTC，成功）。
- [x] 10. 假設 PR 的 CI 失敗，當在 PR 頁面看合併按鈕，則不能合併（本人在 GitHub 設定分支保護後人工確認）。
  - 2026-10-16 用 GitHub API 確認設定：`main` 的 ruleset 啟用、必須通過 `backend`、`frontend`。2026-10-16 試驗 PR #42（目標 `main`、故意讓 ruff 失敗）：API 回 `BLOCKED`，本人確認合併按鈕是灰的；PR 已關閉、分支已刪。
- [x] 11. 假設 PR 合併進 `main`，當 Render 準備部署，則等 `main` 上的 CI 通過才部署（本人在 Render 設定後，看部署紀錄人工確認）。
  - 2026-10-16：合併 13:00:33、CI 結束 13:01:34、Render「Deploy started」1:01 PM（只到分鐘）、gunicorn 13:02:47。沒等 CI 的話會顯示 1:00 PM；跟等 CI 相符。沒有實際做「`main` 的 CI 失敗時不部署」（要把壞程式合進 `main`，代價太大）。
- [x] 12. 假設同一個 PR 的 CI 還在跑，當再推一個 commit，則舊的那次被取消，只有最新的跑完。

驗證方式：CI 本身沒辦法用 `tests.py` 測，驗收 2–5、10、12 用「試驗」做：從這條分支另開丟棄用分支，故意弄壞、開 PR 看 CI 變紅（驗收 10 的 PR 目標是 `main`，才會受分支保護規則管），確認後關掉 PR、刪掉分支。故意弄壞的東西不進這條分支，也不需要改寫歷史。

## 6. 待決問題

- [x] ~~1. 什麼時候跑？~~ → 開 PR、PR 有新 push、合併進 `main` 後（2026-10-16）
- [x] ~~2. CI 沒過要不要擋合併？~~ → 擋，GitHub 分支保護由本人設定，AI 提供步驟（2026-10-16）
- [x] ~~3. CI 沒過要不要擋 Render 部署？~~ → 擋，Render「CI 通過後才部署」由本人設定（2026-10-16）
- [x] ~~4. 連續推兩次？~~ → 取消舊的，只跑最新的（2026-10-16）

---

## 完成後回報（由 AI 填寫）

- **改了哪些檔案、為什麼**：
  - `.github/workflows/ci.yml`（新增）：`backend`（PostgreSQL 18 服務容器、`ruff check`、Django 測試）與 `frontend`（前端測試、建置）兩個 job 平行跑；觸發是 PR 和 push 到 `main`；權限唯讀；PR 取消舊的、`main` 每個 commit 自成一組；前一步失敗後面照跑。
  - `docs/reviews/phase-06/phase6_ci_plan.md`、`phase6_ci_review.md`：計畫與審查。
- **驗收條件對應的測試**：CI 不能寫進 `tests.py`，改用試驗：
  - 1、6、8、9 前半：PR #40 的 CI 紀錄（Django 333、前端 135 通過；PostgreSQL 18.6、Python 3.13.15、Node v24.21.0；只 push 沒開 PR 時沒跑）
  - 2–5：試驗 PR #41（一個 commit 弄壞四處，四項都紅、各自有錯誤訊息）
  - 7：檢查設定檔
  - 10：試驗 PR #42（目標 `main`，`BLOCKED`，本人看到按鈕灰色）
  - 12：PR #41 連推兩次，舊的 `cancelled`
  - 9 後半、11：合併後確認（見上方各條）
- **規格以外的決定**：
  - 驗證方式從「在本分支弄壞、合併前拿掉 commit」改成「另開丟棄用分支、開 PR、做完關掉刪除」：不用改寫歷史。
  - CI 設 `DEBUG=True`：`settings.py` 在 DEBUG 關閉時要 `SECRET_KEY` 並開 HTTPS 轉址，測試會全部 301；本機一直靠 `.env` 的 `DEBUG=True`。
  - 官方元件寫到確切版本、挑發布滿兩週的（setup-node 用 v7.0.0，不用 10-08 的 v7.1.0）。
  - 審查後：`main` 的 concurrency 改成每個 commit 一組（原本同組最多一個排隊，連合三次中間那次會被擠掉）。
- **這次用到的新概念**：CI、workflow／job／step、服務容器、`!cancelled()`、concurrency group、ruleset 與必要檢查、Render「After CI Checks Pass」、Render 部署的 Build／Deploy 兩段（完整說明見 `docs/interview.md`「CI 與部署」）
- **面試可能追問的 2–3 題**：Q72 為什麼用 PostgreSQL 18、`DEBUG` 的坑；Q73 `main` 為什麼不取消舊的；Q74 怎麼證明 CI 擋得住（要點見 `docs/interview.md`）
- **建議寫進 decisions/ 的內容**：見對話（素材由本人撰寫）
- **觀察到沒改**：CI 的 Django 測試會印 `UserWarning: No directory at: .../staticfiles/`（CI 沒跑 collectstatic，本機有這個資料夾）；不影響結果。
