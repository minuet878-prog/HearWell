# Phase 6 規格：正式環境不裝開發工具

- **狀態**：已完成（驗收 5 待合併部署後確認）
- **分支**：`chore/ruff-dev-only`
- **擬稿**：AI　　**確認人**：本人　　**確認日期**：2026-10-16

> 給 AI 的說明：本規格狀態為「已確認」之前，不得開始實作。
> 規格沒寫到、而且會影響行為的地方，先停下來問，不要自行決定。

---

## 1. 目標

正式環境只裝網站執行時真正需要的套件。開發工具（`ruff`）只在本機和 CI 裝，部署更小、更快，也少一個要追蹤更新的東西。
網站的行為完全不變。

## 2. 範圍

### 要做
- `ruff` 從正式環境的套件清單移到開發用清單；本機和 CI 照樣有 `ruff` 可以用
- `click`、`h11` 一起從正式清單移除（只有沒在用的 `uvicorn` 會用到）
- CI 多一道檢查：乾淨環境只裝正式清單，跑跟部署時一樣的 Django 系統檢查
- 順手補：`phase6_ci.md` 驗收 9 後半、11 打勾（合併後已確認，`main` 受保護只能在這裡補）

### 不做
- 升級任何套件版本
- 改用其他套件管理工具（Poetry、uv、`pyproject.toml` 的 dependencies 等）
- 整理本機虛擬環境（本機多裝的 `uvicorn` 不動，那是你的環境）
- 改 `build.sh` 的流程、改 Render 設定
- 其他 Phase 6 項目（`ALLOWED_HOSTS` 等）

## 3. 必須遵守的規則

- 一律遵守 CLAUDE.md「不可違反的規則」。
- 本 phase 特別注意：
  - 合併後部署一次才算驗收完成；部署失敗時 Render 會繼續跑舊版本，不會中斷服務

## 4. 行為描述

### 4.1 套件清單

| 項目 | 內容 |
|---|---|
| 正式環境（Render）會裝 | 網站執行需要的套件；不含 `ruff`、`click`、`h11` |
| 本機、CI 會裝 | 正式環境的全部＋開發工具（`ruff`、debug-toolbar） |
| 網站行為 | 不變 |

## 5. 驗收條件

- [x] 1. 假設只裝正式環境的清單，當列出已安裝的套件，則沒有 `ruff`。
- [x] 2. 假設裝開發用清單，當執行 `ruff check .`，則可以執行而且通過。
- [x] 3. 假設這次的 PR，當 CI 跑完，則 `backend`、`frontend` 都通過（`ruff` 那一步有實際執行，不是被跳過）。
- [x] 4. 假設只裝正式環境的清單（乾淨的虛擬環境），當執行 Django 的系統檢查（用正式環境的設定、假的環境變數），則沒有錯誤，所有 app 都載入得到。
- [ ] 5. 假設合併後 Render 部署，當看部署紀錄，則安裝清單裡沒有 `ruff`，部署成功、網站正常回應。
- [x] 6. 假設只裝正式環境的清單，當列出已安裝的套件，則沒有 `click`、`h11`。
- [x] 7. 假設 PR 的正式清單完整，當 CI 跑完，則「只裝正式清單」的檢查通過，紀錄裡看得到它是在乾淨環境、只裝正式清單。
- [x] 8. 假設網站需要的套件被放進開發用清單、不在正式清單（例如把 `whitenoise` 搬過去），當 CI 跑完，則 Django 測試照樣通過，但「只裝正式清單」的檢查失敗，看得到缺哪個套件。
  - 第一次試驗（只有 `check --deploy`）沒抓到：它不會載入 middleware。加上 `gunicorn --check-config config.wsgi` 後，試驗 PR #44 變紅、紀錄有 `No module named 'whitenoise'`；PR 已關、分支已刪。

## 6. 待決問題

- [x] ~~1. `click`、`h11` 要不要一起移除？~~ → 一起移除（2026-10-16）
- [x] ~~2. CI 要不要多一道「只裝正式清單也能啟動」的檢查？~~ → 要（2026-10-16）

---

## 完成後回報（由 AI 填寫）

- **改了哪些檔案、為什麼**：
  - `requirements.txt`：刪 `ruff`、`click`、`h11`；`requirements-dev.txt`：加 `ruff==0.16.1`（版本不變）
  - `.github/workflows/ci.yml`：`backend` 加「Production dependencies」：乾淨虛擬環境只裝正式清單 → `check --deploy --fail-level WARNING` → `gunicorn --check-config config.wsgi`
  - `README.md`、`claude.md`：開發清單多了 ruff 的說明；`docs/specs/phase6_ci.md`：驗收 9、11 打勾
- **驗收條件對應的測試**：
  - 1、4、6：scratchpad 乾淨虛擬環境，改前有三個套件（確認失敗），改後沒有、`check --deploy` 通過
  - 2：本機 `py313/bin/ruff check .`；3、7：PR #43 的 CI 紀錄
  - 8：試驗 PR #44（見該條註記）
  - 5：合併部署後確認
- **規格以外的決定**：
  - 加 `gunicorn --check-config`：第一次試驗發現 `check --deploy` 不載入 middleware，抓不到缺 `whitenoise`（本人同意後追加）
  - 檢查放在既有 `backend` job，不另開 job：分支保護的必要檢查不用改
  - 審查 3-1（以後把 ruff 加回正式清單 CI 不擋）：不加，規格沒要求
- **這次用到的新概念**：requirements 清單不是鎖定檔、`check --deploy` 的範圍、`gunicorn --check-config`、開發清單是正式清單的超集合（完整說明見 `docs/interview.md`）
- **面試可能追問的 2–3 題**：Q75 CI 全綠為什麼正式環境可能少套件；Q76 `check --deploy` 為什麼抓不到 whitenoise；Q77 檢查第一次沒變紅怎麼辦
- **建議寫進 decisions/ 的內容**：見對話（素材由本人撰寫）
- **觀察到沒改**：`brotli` 只在 `collectstatic` 壓縮時用到，這道檢查抓不到它
