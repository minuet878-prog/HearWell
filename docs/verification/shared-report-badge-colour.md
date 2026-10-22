# 家人分享報告「先看重點」的程度標籤沒有顏色

日期：2026-10-23；分支 `fix/shared-report-badge-colour`（從 `main` `0a35944` 開出）。
狀態：自動驗證完成；不需交叉審查（只改樣板傳給標籤的參數名稱，不碰計分、門檻、資料或權限）。

## 問題與根本原因

- 現象：家人打開分享報告，「先看重點」卡裡生活影響問卷的分級、兩耳的程度標籤都沒有分級顏色與外框。
- 原因：`shared_report.html` 兩處用 `level=` 把分級傳給 `level_badge.html`，但這個樣板讀的是 `color`，所以 class 變成空的 `level-badge-`。#194 加這張卡時寫錯，當時的測試只比對拿掉標籤後的文字，沒有驗 class。
- 發現經過：#201 結果頁也用到 `level_badge.html`，對照寫法時看到的。

## 修正

- `shared_report.html` 兩處改成 `color=`。
- 同一個原因的其他地方：全專案 8 處 `level_badge.html` 現在都傳 `color=`，沒有別處寫錯。
- 「先看重點」卡本來就不列印，列印版不受影響。

## 驗證

| 項目 | 結果 |
|---|---|
| 重現測試 `test_shared_report_highlights.py` 的 `test_badges_carry_their_level_colour` | 修之前失敗（三個標籤都是 `level-badge-`），修之後通過：顯著影響 `severe`、中度 `mild_to_moderate`、資料不足 `unknown` |
| Django 全部 | 1003 個通過 |
| e2e `e2e.main_flow` 全套 | 95 個通過 |
| Ruff check／format | 通過 |

## 請本人驗收

- [ ] 產生分享連結，用無痕視窗打開家人報告：「先看重點」裡問卷分級和兩耳程度的標籤，顏色跟本人的結果頁、聽力圖頁一樣。
