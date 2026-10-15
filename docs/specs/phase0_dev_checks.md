# Phase 0 規格：開發與上線前檢查（debug-toolbar、check --deploy）

- **狀態**：已完成（驗收 1、10、11 待本人人工確認；合併前確認 Render 的 SECRET_KEY 強度與沒有設 PYTHON_VERSION）
- **分支**：`chore/phase0-checks`
- **擬稿**：AI　　**確認人**：本人　　**確認日期**：2026-10-15

> 給 AI 的說明：本規格狀態為「已確認」之前，不得開始實作。
> 規格沒寫到、而且會影響行為的地方，先停下來問，不要自行決定。

---

## 1. 目標

收掉 Phase 0 剩下的檢查工具：本機開發時看得到每頁跑了哪些 SQL（debug-toolbar），上線前有固定的方法確認正式環境的安全設定（`check --deploy`）。兩者都不能影響正式環境的使用者。

## 2. 範圍

### 要做
- debug-toolbar：只在本機 `DEBUG=True` 時出現在頁面上；只裝在本機（開發用套件另列一份清單），正式環境裝的套件不變。
- HSTS：開啟，時效先設 1 小時；子網域一起適用（`SECURE_HSTS_INCLUDE_SUBDOMAINS`）；不申請瀏覽器內建名單（`SECURE_HSTS_PRELOAD`），並明確略過這個警告、寫下理由。
- `check --deploy`：每次部署自動跑，有任何警告就讓部署失敗。
- 鎖定正式環境的 Python 版本為 3.13.15（跟本機測試環境一致；Render 原本自動用 3.14.3）。
- roadmap 加 HSTS 時效拉長的待辦：1 小時 →（1 週沒問題）1 天 →（再 1 週）1 週 → 1 年。

### 不做
- 改任何頁面、計分、API 的行為。
- 其他效能或除錯工具（例如 django-silk、Sentry）。
- 改 `DEBUG`、`SECRET_KEY`、SSL 導向、cookie 的現有設定（2026-09-01、09-24 的決定）。
- 這次就把 HSTS 拉長到 1 天以上；申請 HSTS preload。
- 自訂網域、資料庫、其他部署平台設定。

## 3. 必須遵守的規則

- 一律遵守 CLAUDE.md「不可違反的規則」。
- 本任務特別注意：
  - debug-toolbar 不能在正式環境出現，正式環境也不裝它。
  - 測試時不能載入 debug-toolbar（它會讓測試變慢或報錯）。
  - HSTS 只在 `DEBUG=False` 時送出（本機開發維持 HTTP，不被瀏覽器記住）。
  - 略過的檢查只能是 W021，而且要在設定旁寫理由；不能用「略過」處理其他警告。
  - 不自己啟動或停掉伺服器；本機看 toolbar 由本人啟動。
  - 密碼、金鑰只放 `.env`；部署檢查用 Render 上已設定的環境變數，不寫假金鑰進程式碼。

## 4. 行為描述

### 4.1 debug-toolbar

| 項目 | 內容 |
|---|---|
| 出現的條件 | 本機、`DEBUG=True`、裝了開發用套件 |
| 顯示的內容 | 套件預設面板（SQL 查詢、時間、模板、設定等） |
| 不能出現的地方 | 正式環境、測試、`DEBUG=False` 的任何環境；開發用套件沒裝時網站照常運作 |

### 4.2 HSTS

| 項目 | 內容 |
|---|---|
| 回應標頭 | `DEBUG=False` 時每個回應都有 `Strict-Transport-Security: max-age=3600; includeSubDomains`，沒有 `preload` |
| `DEBUG=True` | 不送這個標頭 |

### 4.3 check --deploy

| 項目 | 內容 |
|---|---|
| 怎麼跑 | 部署建置時，用正式環境的設定（`DEBUG=False`）執行，警告也算失敗 |
| 預期結果 | 0 個警告（W021 明確略過） |
| 失敗時 | 部署停止，正式站維持舊版本 |

## 5. 驗收條件

**debug-toolbar**
- [ ] 1. 假設 `DEBUG=True` 且裝了開發用套件，當打開任何頁面，則頁面上有 debug-toolbar。（人工，本人在本機看）
- [x] 2. 假設 `DEBUG=False`，當打開任何頁面，則沒有 debug-toolbar，也連不到它的網址。
- [x] 3. 假設跑測試，則不載入 debug-toolbar，現有測試全部通過。
- [x] 4. 假設 `DEBUG=True` 但沒裝開發用套件（例如正式環境的套件清單），則網站照常啟動、不報錯。
- [x] 5. 正式環境的套件清單裡沒有 debug-toolbar。

**HSTS 與 check --deploy**
- [x] 6. 假設 `DEBUG=False`，當請求任何頁面，則回應有 `Strict-Transport-Security: max-age=3600; includeSubDomains`，沒有 `preload`。
- [x] 7. 假設 `DEBUG=True`，則回應沒有 `Strict-Transport-Security`。
- [x] 8. 假設 `DEBUG=False`，當跑 `check --deploy`（警告也算失敗），則 0 個問題；略過的只有 W021，設定旁有理由。
- [x] 9. 假設部署建置時 `check --deploy` 有任何警告，則建置失敗（建置腳本裡的順序與參數）。
- [ ] 10. （人工）合併部署後，Render build log 有 `check --deploy` 通過的紀錄；正式站回應標頭有 HSTS；網站正常。

**Python 版本**
- [ ] 11. （人工）合併部署後，Render build log 顯示 Python 3.13.15，網站正常。

## 6. 待決問題

- ~~1. HSTS~~ → 開啟，先 1 小時，逐步拉長（2026-10-15）
- ~~2. check --deploy 時機~~ → 每次部署自動跑，有警告就失敗（2026-10-15）
- ~~3. Python 版本鎖定~~ → 一起做（2026-10-15）
- ~~4. 正式環境裝不裝 toolbar~~ → 不裝，開發用套件另列清單（2026-10-15）
- ~~5. W005 子網域~~ → 開（目前沒有子網域；改用自訂網域時重新評估）（2026-10-15）
- ~~6. W021 preload~~ → 明確略過並寫理由（`onrender.com` 是共用網域，無法申請）（2026-10-15）
- ~~7. HSTS 拉長時程~~ → 1 小時 → 1 天 → 1 週 → 1 年，每階段觀察 1 週（2026-10-15）
- ~~8. 鎖哪個 Python 版本~~ → 3.13.15，跟本機測試一致（Render 原本 3.14.3，會退回 3.13）（2026-10-15）

---

## 完成後回報（由 AI 填寫）

- **改了哪些檔案、為什麼**：
  - `requirements-dev.txt`（新）：`-r requirements.txt` 加 `django-debug-toolbar==8.0.0`，只有本機裝；`requirements.txt` 不動。
  - `config/settings.py`：`if not DEBUG:` 區塊加 HSTS（3600 秒、含子網域）；`DEBUG=True` 而且 `import debug_toolbar` 成功時才啟用 toolbar；`SILENCED_SYSTEM_CHECKS = ["security.W021"]` 附理由。
  - `config/test_settings.py`：把 toolbar 從 app 與 middleware 拿掉（本機 `.env` 是 `DEBUG=True`）。
  - `config/urls.py`：toolbar 有啟用時才掛它的網址。
  - `build.sh`：`pip install` 之後馬上 `check --deploy --fail-level WARNING`，在前端建置、collectstatic、migrate、loaddata 之前。
  - `.python-version`（新）：`3.13.15`。
  - `claude.md`：常用指令加 `pip install -r requirements-dev.txt`（本人同意）。
- **驗收條件對應的測試**（`DevChecksTests`）：
  - 1 人工；2、6 `test_production_settings`（另開程序：沒有 toolbar、`/__debug__/render_panel/` 解析不到、HTTPS 回應標頭 `max-age=3600; includeSubDomains`）；3 `test_tests_never_load_toolbar`；4、7 `test_debug_without_dev_packages_still_works`；5 `test_toolbar_only_in_dev_requirements`；8 `test_deploy_check_passes_with_warnings_as_errors`；9 `test_build_runs_deploy_check_before_anything_changes`；10、11 人工
  - 另外：`test_production_python_matches_tests`（`.python-version` 等於跑測試的 Python）
  - 結果：Django 212、前端 31 全部通過
- **規格以外的決定**（如果有，說明原因）：
  - 「DEBUG=False 時的設定」用另開的 Python 程序測：設定檔載入時就算好，`override_settings` 不會重跑 `if not DEBUG:`。程序只讀設定、發一個不碰資料庫的 API 請求。
  - 「沒裝 toolbar」用 `sys.modules["debug_toolbar"] = None` 模擬，不用真的解除安裝。
  - 已知待辦（不在範圍）：`ruff` 在正式套件清單、`ALLOWED_HOSTS` 空字串時 `check --deploy` 抓不到。
- **這次用到的新概念**（各用一句話解釋）：HSTS 與 max-age、`includeSubDomains`、preload 名單、`check --deploy` 與 `--fail-level`、`SILENCED_SYSTEM_CHECKS`、開發用套件清單（`-r`）、選用相依（try import）、`.python-version`、設定在載入時就算好（要另開程序測）、`sys.modules` 模擬沒裝套件。說明見 `docs/interview.md`。
- **面試可能追問的 2–3 題**（附答案要點）：Q54 HSTS 為什麼要從 1 小時開始；Q55 為什麼 `check --deploy` 放在建置最前面、而且警告也算失敗；Q56 怎麼測「正式環境的設定」和「沒裝某個套件」。要點見 `docs/interview.md`。
- **建議寫進 decisions/ 的內容**（素材即可，條目由本人撰寫；註明放哪個主題檔）：
  - `security.md`：HSTS 開啟（推翻 09-01「先不加」）：Render HTTPS 穩定一個多月；從 1 小時開始逐步拉長；含子網域（目前沒有子網域）；不 preload（共用網域無法申請），W021 明確略過。
  - `deploy.md`：每次部署先跑 `check --deploy --fail-level WARNING`，放在 migrate 之前；坑：正式 `SECRET_KEY` 以前從沒被檢查過強度（W009）。
  - `deploy.md`：Python 鎖 3.13.15（Render 沒鎖時自動用了 3.14.3，跟測試版本不一致）。
  - `tooling.md`：debug-toolbar 只裝本機（`requirements-dev.txt`）；測試設定要排除它；坑：`/__debug__/` 本身不是 toolbar 的網址，測「連不到」要用子路徑。
