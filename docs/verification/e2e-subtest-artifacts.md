# e2e：subTest 裡的失敗也保存截圖與 trace

日期：2026-10-22。來源：PR #144（2a 共用外殼）的 CI e2e 失敗發生在 `subTest` 裡，CI 上傳不到任何 `e2e-artifacts/`。沒有另開規格 issue。分支：`fix/e2e-subtest-artifacts`。

狀態：自動驗證完成，等本人驗收。只改 `e2e/main_flow.py` 的測試工具，不改網站程式。不需交叉審查（沒碰計分、門檻、migration、權限）。

## 根本原因

`saving_artifacts()` 只在例外穿出 `with` 區塊時存檔。`subTest` 失敗時 unittest 會自己記下失敗、接著跑後面的程式，例外不會往外傳，外層的 `saving_artifacts()` 看不到，所以什麼都沒存。

## 改法

- 新增 `SavesFailureArtifacts`（四個 e2e 測試類別共同繼承，取代原本 `saving_artifacts = NewUserScreeningTest.saving_artifacts` 的借用寫法）。
- 它把 `subTest` 包一層：子測試裡的失敗在被 unittest 攔下之前，先經過 `saving_artifacts()`，存下**失敗當下**那個瀏覽器的截圖與 trace。
- 同一個瀏覽器 context 只存第一次失敗：Playwright 的 trace 停過一次再停會丟錯（實測：`Tracing.stop: Must start tracing before stopping`），若不防，`saving_artifacts()` 包在 `subTest` 裡面的寫法（例如 `test_trend_dates_stay_inside_and_apart`）或同一頁兩個子測試都失敗時，會多出一個假錯誤蓋掉真正的失敗。
- 檔名不變（`failure.png`、`trace.zip`），CI workflow 不用改。

## 驗證

先重現、再修。用暫時的測試檔（試驗，已刪除）逐一單獨跑：

| 情況 | 修改前 | 修改後 |
|---|---|---|
| `saving_artifacts()` 裡有一個失敗的 `subTest` | FAILED (failures=1)，**沒有** `e2e-artifacts/` | FAILED (failures=1)，有 `failure.png`、`trace.zip` |
| `subTest` 裡面包 `saving_artifacts()`，裡面失敗 | — | failures=1，只回報原本的 AssertionError，有兩個檔案 |
| 同一頁兩個 `subTest` 都失敗 | — | failures=2，兩個都是原本的 AssertionError，沒有 Playwright 錯誤，有兩個檔案 |
| `subTest` 通過 | — | OK，沒有 `e2e-artifacts/` |

- 修改後的截圖是失敗當下的頁面（`/privacy`），trace 裡有前往該頁的紀錄。
- 上表先在舊 main（`a73d9c9`）跑；合併新 main（`adb4e42`，含 PR #144）後，第 1、3 種情況再跑一次，結果相同。
- 完整 e2e（合併新 main 後）：`Ran 66 tests in 94.504s`、`OK`，沒有產生 `e2e-artifacts/`。
- `ruff check`、`ruff format --check` 通過。

## 已知限制（沒有在這次處理）

- 檔名固定，同一次執行有多個失敗時，後面的會蓋掉前面的（修改前跨測試就是這樣；現在子測試也會存，比較容易遇到）。若要每個失敗各留一份，可以改用測試名稱命名，CI 的上傳路徑不用改。
