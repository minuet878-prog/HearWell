# e2e 讀動畫狀態的時間競爭

日期：2026-11-05；分支 `fix/meter-fill-test-race`（從 `main` 的 `b2b31d1` 開出）。
狀態：只改測試和文件，自動驗證完成；**不需交叉審查**（不碰計分、門檻、資料或權限）。

## 起因

PR #422 合併後，`main` 的 e2e 失敗：`test_without_javascript_meters_fill_on_arrival` 要求儀表動畫是 `running`，實際是 `finished`。合併後的內容和 PR 最後一個 commit 完全相同（tree `987eaa8`），PR 上 e2e 是通過的，所以不是改名造成的。

## 根本原因

這些測試要驗「沒有 JavaScript 時，動畫不等畫面」，但寫成「讀取當下必須正在跑」。動畫很短（儀表 1.2 秒、`gauge-draw` 約 0.55 秒），機器慢一點，讀到時已經跑完，功能是對的，測試卻失敗。

## 修法

只有等待畫面的動畫才會是 `paused`，所以改成「有動畫，而且沒有 `paused`」。同樣寫法的三個測試一起改：

- `test_without_javascript_meters_fill_on_arrival`
- `test_without_javascript_animations_play_on_arrival`
- `test_double_text_gauge_waits_and_header_wave_plays_at_once` 裡頁首波浪的檢查（同一個測試裡，儀表要 `paused` 的檢查不變）

沒改：`e2e/main_flow.py` 讀 `animation-play-state` 的檢查（讀 CSS 屬性，動畫跑完也不變），以及 `wait_until(..., "running")`（會一直等到狀態出現）。

## 驗證

都是試驗，做完已還原：

| 條件 | 預期 | 結果 |
|---|---|---|
| 修之前，讀狀態前等 6 秒 | 失敗 | 3 個都失敗，訊息和 CI 相同 |
| 修之後，讀狀態前等 6 秒 | 通過 | 3 個都通過 |
| 修之後，不等待 | 通過 | 3 個都通過 |
| 修之後，兩個「沒有 JavaScript」的測試改成有 JavaScript | 失敗 | 2 個都因 `paused` 失敗，真正的錯誤還抓得到 |

全套結果見 PR。
