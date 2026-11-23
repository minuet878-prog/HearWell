# 驗證紀錄 — Batch 4：前端套件安全盤點與 CI `e2e-gate` 閘道工作

- 分支：`chore/frontend-security-updates-and-ci-check`（自 `main` `e5a90336` 分出）
- 日期：2026-11-23
- 交叉審查：不需交叉審查（未觸及計分／分級、門檻、會動資料的 migration 或權限規則）

## 變更摘要

1. **前端套件安全盤點（無需修改 `package.json`）**
   - 核對 `frontend/package.json` 與 `frontend/package-lock.json`：PR #737（2026-11-19）已將 `vite` 升至 `8.3.8`、`undici` 升至 `8.12.4`、`jsdom` 維持 `30.1.1`。
   - 實測 `npm audit --prefix frontend` 為 **0 弱點**（prod 43 ＋ dev 155，共 198 個依賴套件）。
   - 本機 `frontend/node_modules/` 已透過 `npm ci --prefix frontend` 同步至 `vite 8.3.8`。
2. **新增 `.github/workflows/ci.yml` 的 `e2e-gate` 閘道工作**
   - `e2e` 是 3 分片矩陣工作（`e2e (1/3)`、`e2e (2/3)`、`e2e (3/3)`），且純文件 PR 會跳過它；若直接把三個分片名稱加入 GitHub Ruleset，純文件 PR（如 `scripts/ship_docs.py`）會因矩陣未展開而永久 pending。
   - 新增單一彙整工作 `e2e-gate`（`needs: [changes, e2e]`、`if: ${{ always() && !cancelled() }}`），透過環境變數檢查 `changes` 為 `success` 且 `e2e` 為 `success` 或 `skipped`，兼顧純文件 PR 放行與程式碼 PR 任一分片失敗即阻擋。

## 驗證結果

| 項目 | 指令／檢查方式 | 結果 |
|---|---|---|
| 前端套件安全掃描 | `npm audit --prefix frontend --json` | **0 vulnerabilities**（total: 0） |
| CI YAML 語法與結構 | `yaml.safe_load(".github/workflows/ci.yml")` | 通過（jobs：`changes`、`backend`、`frontend`、`e2e`、`e2e-gate`） |
| 純文件發布相容檢查 | 檢視 `scripts/ship_docs.py` | 通過（`gh pr checks --watch` 會等 `e2e-gate` 在 `e2e=skipped` 時 5 秒通過後合併） |
| 歷史穩定度盤點 | `gh run list --workflow=ci.yml`（近 25 次 `main` 與近 20 次 PR） | `main` 0 次偶發失敗；PR #761 曾出現 1 次 `SlidingPillTest` 偶發跳紅 |

## 負責人合併後操作清單

- [ ] 本分支開 PR 後，在 GitHub Actions 確認 `e2e-gate` 出現在 PR 檢查清單並正常回報通過
- [ ] 合併回 `main` 後，若要啟用強制攔截，到 GitHub Repository → Settings → Rules → Rulesets → `main`（id `25217841`），在 Required status checks 新增 `e2e-gate`（整合來源 GitHub Actions），不要直接加入 `e2e (1/3)`～`(3/3)`
