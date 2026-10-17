# 4a 首頁：審查報告與查證

規格：[phase9_ui_refresh_4a_home.md](../specs/phase9_ui_refresh_4a_home.md)　基準：`git diff main`（未 commit 的工作目錄）　審查：`reviewer` subagent（2026-10-18）

## reviewer 結論（摘要）

實作符合規格，沒有違反規則。示意圖走 `classify`／`max_score`／`get_advice`，首頁沒有查詢，「不做」清單都沒做。兩項發現如下。reviewer 沒有權限跑 e2e，第 8 條由主 session 跑過（12 OK）。

## 查證與分類

### 要修 1：200% 字級時，步驟卡片撐出左右捲動
- reviewer：`minmax(12rem, 1fr)` 的最窄寬度 12rem，在 200% 字級時約 432px，比 320px 手機的可用寬度大，格線縮不下去。
- **已重現**：用 Chromium 在 320px 寬、把根字級放大成 2 倍（`html{font-size:225%}`，網站原本是 112.5%）。
  - 現在：頁面寬 459px、卡片寬 432px → 要左右捲動。
  - 改成 `minmax(min(12rem, 100%), 1fr)`：卡片寬 266px，剛好放得進去。
- 修法：一行 CSS。另補一個 e2e 測試：200% 字級、320px 寬時，步驟卡片的右邊不能超出畫面（現在的寫法會失敗，已用上面的試驗確認）。

### 不改 2：驗收 7 只驗 class，沒驗算出來的顏色
- 同意 reviewer：Django 測試讀不到 CSS 算出來的顏色；顏色在人工驗收 9 看一眼就能確認，另寫 e2e 不划算。

### 另記（不在這次範圍，建議另開一項）
- **頁尾的 email 連結在 200% 字級時撐到 394px**：`main` 分支也一樣，所以每一頁都有這個問題，不是這次造成的。這也是為什麼補的測試只檢查卡片，不檢查整頁寬度。
- **`.ear-results` 的 `minmax(14rem, 1fr)`**（聽力圖結果）寫法一樣，可能有同樣的問題，沒有實際重現。

## 處理結果（本人同意，2026-10-18）

- 要修 1：已修（`styles.css` `.step-cards` 改 `minmax(min(12rem, 100%), 1fr)`）。補 e2e `test_home_step_cards_fit_a_phone_at_double_text_size`：修之前失敗（459 > 320），修之後通過。548＋13 e2e 全過。
- 另記兩項：照建議另開，收尾時寫進 roadmap。
