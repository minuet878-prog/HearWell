# Phase 6 規格：`ALLOWED_HOSTS` 設錯時部署要停下來

- **狀態**：已完成
- **分支**：`fix/allowed-hosts-empty`
- **擬稿**：AI　　**確認人**：本人　　**確認日期**：2026-10-16

> 給 AI 的說明：本規格狀態為「已確認」之前，不得開始實作。
> 規格沒寫到、而且會影響行為的地方，先停下來問，不要自行決定。

---

## 1. 目標

`ALLOWED_HOSTS`（網站願意回應的網址清單）在正式環境設錯時，部署在建置階段就失敗、說清楚錯在哪，
舊版本繼續服務；不要等到上線後每個請求都回 400 才發現。本機開發（`DEBUG=True`）的行為不變。

## 2. 範圍

### 要做
- 正式環境（`DEBUG` 不是 True）：
  - 環境變數完全沒設 → 啟動失敗，中文錯誤訊息（跟 `SECRET_KEY` 同一套做法）
- 不分本機或正式環境：設了但整理後沒有任何網址（空字串、只有空白、只有逗號）→ 啟動失敗
- 每個網址前後的空白去掉；空的項目丟掉
- 順手補：`phase6_ruff_dev_only.md` 驗收 5 打勾、狀態改「已完成」（本人看 Render 部署紀錄確認）

### 不做
- 檢查網址格式本身對不對（例如拼錯字）：只管「有沒有」「空白」
- 改 `CSRF_TRUSTED_ORIGINS` 或其他安全設定
- 改 Render 的環境變數（目前的值已符合新規則）
- 改 `build.sh` 流程
- 其他 Phase 6 項目

## 3. 必須遵守的規則

- 一律遵守 CLAUDE.md「不可違反的規則」。
- 本 phase 特別注意：
  - Render 目前 `ALLOWED_HOSTS=hearwell.onrender.com`（本人 2026-10-16 確認），符合新規則；合併後部署失敗時舊版本會繼續跑
  - 錯誤訊息裡不印出環境變數以外的設定值

## 4. 行為描述

### 4.1 讀取 `ALLOWED_HOSTS`

| 情況 | 本機（`DEBUG=True`） | 正式環境 |
|---|---|---|
| 沒設 | `127.0.0.1`、`localhost`（不變） | 啟動失敗，訊息說明要設哪個環境變數 |
| `""`、`"  "`、`","` | 啟動失敗 | 啟動失敗，訊息說明要設哪個環境變數、格式是什麼 |
| `"a.com, b.com"` | `a.com`、`b.com` | `a.com`、`b.com` |
| `"a.com,,b.com,"` | `a.com`、`b.com` | `a.com`、`b.com` |

啟動失敗時：部署的建置階段（`build.sh` 裡的 `check --deploy`）就會停下，CI 的「只裝正式清單」檢查也會變紅。

## 5. 驗收條件

- [x] 1. 假設正式環境 `ALLOWED_HOSTS=""`，當啟動 Django，則失敗，錯誤訊息是中文、指出 `ALLOWED_HOSTS`。
- [x] 2. 假設正式環境 `ALLOWED_HOSTS="   "` 或 `","`，當啟動，則跟驗收 1 一樣失敗。
- [x] 3. 假設 `ALLOWED_HOSTS="hearwell.onrender.com, localhost"`，當啟動，則清單是 `hearwell.onrender.com`、`localhost`（沒有前導空白）。
- [x] 4. 假設 `ALLOWED_HOSTS="a.com,,b.com,"`，當啟動，則清單是 `a.com`、`b.com`。
- [x] 5. 假設本機 `DEBUG=True` 而且沒設 `ALLOWED_HOSTS`，當啟動，則清單仍是 `127.0.0.1`、`localhost`。
- [x] 6. 假設這次的 PR，當 CI 跑完，則全部通過（CI 的正式環境檢查有設好 `ALLOWED_HOSTS`）。
- [x] 7. 假設合併後 Render 部署，當看部署紀錄，則建置成功、網站正常回應。
  - 2026-10-16 PR #45 合併（`7783f2a`）後本人確認 Render 部署成功。
- [x] 8. 假設正式環境完全沒設 `ALLOWED_HOSTS`，當啟動，則失敗，錯誤訊息是中文、指出 `ALLOWED_HOSTS`。
- [x] 9. 假設本機 `DEBUG=True` 而 `ALLOWED_HOSTS=""`，當啟動，則跟驗收 1 一樣失敗。
- [x] 10. 假設 `ALLOWED_HOSTS="hearwell.onrender.com"`（Render 目前的值），當用正式環境設定跑 `check --deploy`，則通過。

## 6. 待決問題

- [x] ~~1. 正式環境完全沒設？~~ → 啟動失敗（2026-10-16）
- [x] ~~2. 網址前後有空白？~~ → 自動去掉（2026-10-16）
- [x] ~~3. 有空項目？~~ → 丟掉空的（2026-10-16）
- [x] ~~4. Render 目前怎麼設？~~ → `hearwell.onrender.com`（2026-10-16）
- [x] ~~5. 本機設成空字串？~~ → 一樣報錯；本機沒設仍用預設（2026-10-16）

---

## 完成後回報（由 AI 填寫）

- **改了哪些檔案、為什麼**：
  - `config/settings.py`：讀 `ALLOWED_HOSTS` 的一行改成：沒設時正式環境報錯、本機用預設；去空白、丟空項；整理完是空的就報錯
  - `screening/tests.py`：新增 `AllowedHostsTests`；`DevChecksTests._run` 補 `ALLOWED_HOSTS=localhost`（新規則下正式設定沒設會啟動失敗）
  - `.github/workflows/ci.yml`：「Production dependencies」加 Render 的值；`README.md`、`.env.example`：改成正式環境必填
  - `docs/specs/phase6_ruff_dev_only.md`：驗收 5 打勾
- **驗收條件對應的測試**：1、2 `test_production_rejects_empty_values`；3 `test_spaces_around_hosts_are_removed`；4 `test_empty_items_are_dropped`；5 `test_local_default_when_unset`；8 `test_production_requires_the_variable`；9 `test_local_rejects_empty_value`；10 `test_render_value_passes_deploy_check`；6 PR #45 CI；7 合併部署後確認
- **規格以外的決定**：
  - 測試子行程把 `dotenv` 換成假模組：本機 `.env` 有 `ALLOWED_HOSTS`，不換的話「沒設」測不到
  - 審查 3-1、5-1 不改（見 `docs/reviews/phase6_allowed_hosts_review.md`）
- **這次用到的新概念**：`ALLOWED_HOSTS` 與 Host 標頭、W020 只看清單空不空、環境變數的三種狀態、在新行程裡測設定、換掉 `sys.modules` 裡的模組（完整說明見 `docs/interview.md`）
- **面試可能追問的 2–3 題**：Q78 `ALLOWED_HOSTS` 是什麼、空字串為什麼抓不到；Q79 `is None` 和 `if not` 怎麼選；Q80 怎麼測模組載入時就算好的設定
- **建議寫進 decisions/ 的內容**：見對話（素材由本人撰寫）
