# e2e：subTest 裡的失敗也保存截圖與 trace，每個失敗各留一份

日期：2026-10-22。來源：PR #144（2a 共用外殼）的 CI e2e 失敗發生在 `subTest` 裡，CI 上傳不到任何 `e2e-artifacts/`。沒有另開規格 issue。分支：`fix/e2e-subtest-artifacts`。

狀態：自動驗證完成，等本人驗收。只改 `e2e/main_flow.py` 的測試工具，不改網站程式。不需交叉審查（沒碰計分、門檻、migration、權限）。

## 根本原因

`saving_artifacts()` 只在例外穿出 `with` 區塊時存檔。`subTest` 失敗時 unittest 會自己記下失敗、接著跑後面的程式，例外不會往外傳，外層的 `saving_artifacts()` 看不到，所以什麼都沒存。

## 改法

- 新增 `SavesFailureArtifacts`（四個 e2e 測試類別共同繼承，取代原本 `saving_artifacts = NewUserScreeningTest.saving_artifacts` 的借用寫法）。
- 它把 `subTest` 包一層：子測試裡的失敗在被 unittest 攔下之前，先經過 `saving_artifacts()`，存下**失敗當下**那個瀏覽器的截圖與 trace。
- 同一個瀏覽器 context 只存第一次失敗：Playwright 的 trace 停過一次再停會丟錯（實測：`Tracing.stop: Must start tracing before stopping`），若不防，`saving_artifacts()` 包在 `subTest` 裡面的寫法（例如 `test_trend_dates_stay_inside_and_apart`）或同一頁兩個子測試都失敗時，會多出一個假錯誤蓋掉真正的失敗。
- 檔名改成「類別.測試名稱-序號」，例如 `SharedLayoutTest.test_trend_dates_stay_inside_and_apart-1.png` 與同名 `.zip`（trace）。原本固定叫 `failure.png`、`trace.zip`，後面的失敗會蓋掉前面的；序號區分同一個測試裡開了好幾個瀏覽器頁面、各自失敗的情況。CI 上傳整個 `e2e-artifacts/`，workflow 不用改。

## 驗證

先重現、再修。用暫時的測試檔（試驗，已刪除）跑：

| 情況 | 修改前 | 修改後 |
|---|---|---|
| `saving_artifacts()` 裡有一個失敗的 `subTest` | FAILED (failures=1)，**沒有** `e2e-artifacts/` | failures=1，有該測試的 `-1.png`、`-1.zip` |
| `subTest` 裡面包 `saving_artifacts()`，裡面失敗 | — | failures=1，只回報原本的 AssertionError，一組檔案 |
| 同一頁兩個 `subTest` 都失敗 | — | failures=2，兩個都是原本的 AssertionError，沒有 Playwright 錯誤，一組檔案（第一次失敗） |
| 每個 `subTest` 各開一頁（`/privacy`、`/family`），兩個都失敗 | — | `-1` 的 trace 是 `/privacy`、`-2` 的是 `/family`，互不覆蓋 |
| `subTest` 通過 | — | OK，沒有 `e2e-artifacts/` |

- 前五種情況放在同一次執行：產生 5 組、共 10 個檔案，沒有互相覆蓋。截圖是失敗當下的頁面，trace 裡有前往該頁的紀錄。
- 修改前的重現在舊 main（`a73d9c9`）跑；之後合併新 main（`adb4e42`，含 PR #144），修改後的結果都在新基準上確認。
- 完整 e2e（合併新 main 後）：`Ran 66 tests in 93.720s`、`OK`，沒有產生 `e2e-artifacts/`。
- `ruff check`、`ruff format --check` 通過。
