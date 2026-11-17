# CI 提速：文件 PR 跳過測試、e2e 分兩台機器（小改動，無 issue）

日期：2026-11-17。基準：`d8800abe`（main）；分支：`ci/faster-ci`。

狀態：本機測試與自審通過；CI 上的實際秒數、文件 PR 真的會略過，要等推上去才看得到。只動 CI 與 e2e 的測試載入，
沒碰計分、門檻、資料 migration、權限，不需交叉審查。未操作真實資料；沒有啟動開發伺服器。

## 為什麼做

main 最近 96 次成功的 CI：三個 job 同時跑，整體時間由 e2e 決定。

| 日期 | e2e 測試數 | e2e 測試步驟 | 後端測試數 | 後端測試步驟 |
|---|---|---|---|---|
| 10/27 | 277 | 約 450 秒 | 1622 | 約 105 秒 |
| 11/06 | 374 | 約 380 秒 | 1866 | 約 65–110 秒 |
| 11/12 | 402 | 約 420–550 秒 | 2011 | 約 110–120 秒 |
| 11/17 | 486 | 約 520–610 秒 | 2777 | 約 160–215 秒 |

- 不是哪一次改動突然拖慢，時間跟著測試數成正比增加。
- 本機 `--durations 0`：最大的一組（WhiteCardRuleTest）121 秒，沒有單一組卡住整輪，平行分配正常。
- 最近合併的 60 個 PR 有 37 個只改文件，每個都照跑約 10 分鐘的 e2e，PR 一次、合併後 main 一次；
  `ship_docs.py` 會等全部檢查通過。

## 改了什麼

- `.github/workflows/ci.yml`
  - 新增 `changes` job：比對這次改了哪些檔（PR 用 base，main 用推送前的 commit）。只改 `docs/`、`GLOSSARY.md`
    時，backend 和 e2e 標成略過。`docs/api/` 例外（`test_api` 會讀那裡的 schema）；比對失敗時照跑全部。
  - e2e 改成 matrix 兩組（`E2E_SHARD` = `1/2`、`2/2`），各自再 `--parallel 4`；失敗時上傳的檔名加上組別，
    兩組不會互相蓋掉。
- `e2e/main_flow.py`：新增 `load_tests`。有 `E2E_SHARD` 時依測試類別輪流分組；本機不設就照舊跑全部。

略過會不會擋住合併或部署：GitHub 的必要檢查把略過的 job 當成通過；Render「After CI Checks Pass」的文件寫明
`success`、`neutral`、`skipped` 都算通過，只有「沒有任何檢查」或「有檢查失敗」才不部署。文件 PR 仍有
`changes`、`frontend` 兩個檢查。

## 驗收對照

| 需求 | 驗證 | 證據 |
|---|---|---|
| 只改 `docs/`、`GLOSSARY.md` 時判斷為不用跑 | ✅ 本機執行 | #700 的合併（`docs/roadmap.md`、`docs/verification/issue-633.md`）→ `code=false` |
| 改到程式時照跑 | ✅ 本機執行 | #692 的合併（`screening/models/accounts.py`）→ `code=true` |
| 只改 `docs/api/` 時照跑 | ✅ 本機執行 | 檔名清單 `docs/api/schema.yaml` → `code=true` |
| 比對失敗時照跑 | ✅ 本機執行 | base 設成不存在的 commit → `code=true` |
| 相似檔名不誤判 | ✅ 本機執行 | `GLOSSARY.md.bak`、`docs2/x` → `code=true` |
| 兩組合起來就是全部、不重複 | ✅ 本機執行 | 不分組 495 項；1/2 有 230 項 45 類，2/2 有 265 項 44 類；合併後與全部相同，重複 0 |
| 兩組時間平均 | ✅ 估算 | 用本機各類別秒數模擬：兩組各約 680 秒的測試量，4 程序下約 250／225 秒 |
| 兩組都通過 | ✅ 本機執行 | `--parallel 4`：1/2 共 230 項 141 秒 OK；2/2 共 265 項 128 秒 OK |
| CI 上 e2e 變快 | ⏳ 等 PR 的 CI | 原本 e2e job 約 10 分 |
| 文件 PR 在 CI 上真的略過、仍能合併與部署 | ⏳ 等下一個文件 PR | |

這些都是 CI 設定，沒有寫自動斷言；判斷邏輯用上表的真實 commit 和手造檔名清單驗證。

## 試驗（沒有改動專案檔）

- 關掉 Playwright trace 錄影看會不會變快：本機同一組測試來回在 52–144 秒之間跳，看不出差別，不採用。
- 後端 `--parallel 4`：本機 279 秒 → 154 秒，2777 項全過；這次沒選，沒有改。

## 測試與審查

- `ruff check .`、`ruff format --check .`：全過。
- e2e 兩組如上表全過；只改 CI 與 e2e 載入，沒有重跑後端測試。
- 自審：看過完整 diff，沒有要修的項目。
