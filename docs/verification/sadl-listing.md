# SADL 上線：拿掉 `listed=False`

日期：2026-10-22；分支 `feat/166-list-sadl`（從合併 #205 後的 `main` 分出）。母規格 #166。
狀態：本人看到 Render 部署後正式站沒有 SADL，指示「刪掉開 PR」、「直接做就可」。不需交叉審查（沒有碰計分、分級、門檻、migration、權限）。

## 為什麼正式站原本看不到

`sadl.py` 設了 `listed=False`；`questionnaires.offered()` 只在 `DEBUG` 開著時列出未上架問卷（ADR 0011）。Render 的 `DEBUG` 是關的，所以目錄、作答頁（404）、API 問卷清單、推薦精靈都沒有 SADL。資料庫裡的問卷與題目早就由 `build.sh` 的 `seed_questionnaires` 建好，這次不用動資料。

## 改了什麼

- `screening/questionnaires/sadl.py`：拿掉 `listed=False`（預設 `True`）。
- `listed` 欄位與 `DEBUG` 才顯示的機制保留，ADR 0011 說之後 COSI 等有版權的問卷也要用。
- 測試：
  - 原本「正式站看不到 SADL」的三個測試，改成明確把 SADL 註冊成 `listed=False` 來驗證機制本身。
  - 原本「如果 listed=True 就看得到」改成直接驗證 SADL 在正式站（`DEBUG=False`）出現在目錄、作答頁 200、API 清單。
  - `test_recommendations.py` 的 `assert_ssq12_also`：戴助聽器時「也可以做」現在是 SSQ12＋SADL 兩張卡（#174 原本的設計）。

## 驗收對照

| 條件 | 證明 |
|---|---|
| 正式站目錄看得到 SADL、作答頁可開、API 清單有 SADL | `screening/tests/test_sadl.py:67` `test_sadl_is_offered_in_production` |
| 未上架機制仍有效（給之後的問卷用） | `test_sadl.py:44`、`:56`、`:489` |
| 戴助聽器時推薦精靈「也可以做」列出 SSQ12 與 SADL | `screening/tests/test_recommendations.py:220` `assert_ssq12_also`（`:163`、`:183` 兩個情境） |

## 測試結果

- 全部測試（序列執行）：`Ran 799 tests in 44.822s` `OK`。
- `ruff check .`：All checks passed。
- 平行執行（`--parallel auto`）時 `test_ssq12_comparisons`、`test_standards` 各一個出現 `connection already closed`，單獨重跑通過，跟這次改動無關。

## 待本人確認

- 部署後在 Render 正式站：問卷目錄看得到「助聽器滿意度（SADL）」、可以作答、結果頁顯示子量表。
- ADR 0011 規定上線前要有書面同意或寄信滿 8 週；這次是本人決定直接上線，授權狀態未記錄在這個 PR。
