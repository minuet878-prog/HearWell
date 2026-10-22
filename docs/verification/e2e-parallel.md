# e2e 平行執行（小改動，無 issue）

日期：2026-10-23。基準：`377891d`（main，含 #251）；分支：`ci/e2e-parallel`；commit：`35b96c6`（CI、AGENTS.md、
tblib）、`2d5a488`（子測試失敗不再中斷整輪）、`b8e6c4a`（自審後精簡說明）。

狀態：自動測試與自審（Standards／Spec）已通過，CI 上的實際秒數等 PR 跑完才知道。小改動，只動 CI、測試與開發用套件，
沒碰計分、門檻、資料 migration、權限，不需交叉審查。未操作真實資料；沒有啟動開發伺服器。

## 為什麼做

CI 的 e2e job 約 4 分 40 秒，其中測試本身 223 秒。本機量每個測試的時間（`--durations 0`）：測試本身佔 9 成以上，
清空資料庫、開瀏覽器只有約 10 秒，所以平行執行是最有效的做法。

| 跑法 | 本機時間 |
|---|---|
| 依序（原本） | 140 秒 |
| `--parallel 4` | 約 52–57 秒 |

## 改了什麼

- `.github/workflows/ci.yml`：e2e 改成 `--parallel 4`。Django 以測試類別為單位分給 4 個程序，各自有臨時網站和測試資料庫；
  CI 機器（公開 repo 的 `ubuntu-latest`）是 4 核心。
- `requirements-dev.txt`：加 `tblib==3.2.2`。Django 官方文件：平行時要它才能把失敗的 traceback 傳回主程序。
  試驗：沒裝時一個測試失敗就整輪中斷（`TypeError: cannot pickle 'traceback' object`），看不到出錯的行。
- `e2e/main_flow.py`：`SavesFailureArtifacts.__getstate__` 打包時不帶 `page`、`context`、`saved_context`。
  原因：子測試失敗時，Django 要把測試物件打包傳回主程序；測試進行中 Django 會略過打包不了的屬性，測試結束後就不略過，
  Playwright 的分頁物件讓整輪中斷（`MaybeEncodingError: Can't get local object 'WeakSet…'`），也看不到出錯的行。
- `AGENTS.md`、`e2e/main_flow.py` 檔頭：執行指令加 `--parallel 4`，並註明用 `pdb` 除錯時要拿掉。

## 試驗：子測試失敗時

暫時把 `test_form_9_anchors_jump_to_their_sections` 的標題改成不存在的字，跑 `--parallel 4`，跑完 `git checkout` 還原。

| | 結果 |
|---|---|
| 修正前（2 個類別、`--parallel 2`） | `MaybeEncodingError`，整輪中斷，沒有 `FAIL` 行與行號 |
| 修正後（整套、`--parallel 4`） | 102 項全部跑完，`FAILED (failures=1)`，`FAIL: … (anchor='reapply')`，traceback 指到 `main_flow.py:1925`；`e2e-artifacts/` 有該測試的 `.png` 和 `.zip` |

## 驗收對照

| 需求 | 驗證 | 證據 |
|---|---|---|
| CI 的 e2e 用平行執行 | ✅ 看 diff | `ci.yml` 的 End-to-end test 步驟 |
| 平行時全部測試照常通過 | ✅ 執行結果 | 本機 `--parallel 4` 跑 4 次（合併 #251 後 3 次、自審修改後 1 次），每次 102 項全過（52–57 秒） |
| 失敗時看得到出錯的行 | ✅ 試驗 | 上表「修正後」 |
| 子測試失敗不會中斷整輪 | ✅ 試驗 | 上表「修正前／修正後」 |
| 失敗時仍存截圖與 trace | ✅ 試驗 | 上表「修正後」 |
| AGENTS.md 指令更新 | ✅ 看 diff | `AGENTS.md` 常用指令的端對端測試 |
| CI 上實際變快 | ⏳ 等 PR 的 CI | 原本 e2e 步驟 223 秒 |

這些都是測試基礎設施，沒有寫自動斷言：「失敗時會怎樣」要故意弄壞才看得到，不能留一個永遠失敗的測試。

## 測試與審查

- 端對端 `--parallel 4`：102 項全過（合併 #251 後連跑 3 次，加上自審修改後再跑 1 次）。
- `manage.py test --settings=config.test_settings`：1063 項全過。
- `ruff check .`、`ruff format --check .`：全過。
- 本機要先 `pip install -r requirements-dev.txt` 裝 `tblib`（驗證時用暫存資料夾的副本，沒動 `py313`）。
- 自審（`/mattpocock-skills:code-review`，基準 `origin/main`）：
  - **Standards**：0 項要修；可考慮四項都採納：AGENTS.md 拿掉會過時的秒數並縮短、`e2e/main_flow.py` 檔頭指令補
    `--parallel 4`、只用一次的常數寫回 `__getstate__` 裡。
  - **Spec**：實作沒有錯；要修的是證據（子測試失敗沒有紀錄），已補上方試驗。採納 CI 註解改字（不是「一個類別
    一個程序」，是 4 個程序輪流領類別）。確認排除清單沒有漏、各程序寫的截圖檔名不會撞、`DJANGO_ALLOW_ASYNC_UNSAFE`
    在子程序仍有效。

## 人工驗收

1. 看 PR 的 CI：`e2e` 步驟「End-to-end test」的時間，跟原本約 223 秒比較。
2. 本機（可選）：`pip install -r requirements-dev.txt` 後照 AGENTS.md 的指令跑一次 e2e。
