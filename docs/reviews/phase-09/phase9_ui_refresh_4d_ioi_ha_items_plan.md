# 4d IOI-HA 逐題解讀：實作計畫

規格：[phase9_ui_refresh_4d_ioi_ha_items.md](../../specs/phase-09/phase9_ui_refresh_4d_ioi_ha_items.md)（已確認，2026-10-18）

## 要改的檔案

| 檔案 | 改什麼 |
|---|---|
| `screening/scoring.py` | 新增 `IOI_HA_BELOW_NORM_NOTES = {1: "…", …, 7: "…"}`：4.2 的 7 段定稿文字，跟題目選項、常模表放在一起。只用題號查，規則 9：固定規則、不用 LLM。 |
| `screening/views.py` | `_ioi_ha_items()`（結果頁和報告共用、唯一把作答跟常模比較的地方）每一題多一個 `note`：比較結果是 `below` 時取該題文字，其他情況是 `None`。不另寫一份比較邏輯。 |
| `screening/templates/screening/result_ioi_ha.html` | 在「您的回答」那行後面、同一個 `<li>` 裡，`{% if item.note %}` 才放 `<p class="ioi-note">`；出處區的 include 多傳 `with_notes=True`。 |
| `screening/templates/screening/ioi_ha_source.html` | `{% if with_notes %}` 時多一句「逐題解讀由聽力師依臨床經驗撰寫，不能取代個別諮詢。」。作答頁沒傳這個參數，不會出現。 |
| `screening/static/screening/styles.css` | `.ioi-note`：淡藍底 `#eef3fa`、左邊框主色，跟 4a 首頁的淡藍同色，全部用 `rem`。 |
| 報告模板 | **不動**。報告用同一個 `_ioi_ha_items()`，但模板不印 `note`，所以報告不會出現解讀（6a 用測試確認）。 |

## 驗收條件 → 測試

測試加在 `screening/tests/test_ioi_ha.py` 的 `IoiHaTests`，沿用它現有的 `_hhie_s`／`_post`／`_items`；6a 加在 `test_report.py` 和 `test_share.py`。

| # | 測試 | 怎麼驗 |
|---|---|---|
| 1 | `test_notes_only_on_items_below_norm` | 輕度至中度組，作答 (1,3,1,3,3,3,3)：第 1、3 題各有自己的文字，其他 5 題沒有 `ioi-note` |
| 2 | `test_each_item_gets_its_own_note` | 7 次 subTest：第 n 題答 1（7 題在輕度至中度組都低於常模），其他答 3（都在範圍內）；只出現第 n 段 |
| 3 | `test_no_notes_when_nothing_below_norm` | 全部答 3：頁面上沒有任何一段文字 |
| 4 | `test_no_notes_when_ungrouped` | 沒有 HHIE-S、全部答 1：沒有解讀，有先填 HHIE-S 的提示 |
| 5 | 既有的 `test_other_users_result_is_404` | 不改，跑過確認 |
| 6 | `test_note_inside_item_after_answer` | 文字在同一個 `<li>` 裡、出現在「您的回答」之後 |
| 6a | `test_report.py`、`test_share.py` 各一個 | 現有假資料第 2 題本來就低於常模；自己的報告和家屬分享版都沒有第 2 題的解讀文字 |
| 6b | `test_note_source_only_on_ioi_ha_result` | 有分組、未分組的 IOI-HA 結果頁都有那句；HHIE-S 結果頁、IOI-HA 作答頁沒有 |
| 7 | 人工 | 你看手機 320px、200% 字級，axe，文字內容 |

頁面測試的期望文字從 `scoring.IOI_HA_BELOW_NORM_NOTES` 讀。另外加一個 `test_notes_are_the_confirmed_text`，在測試裡逐字寫一份規格 4.2 的定稿來比對（跟 `test_pages.CopyTests` 檢查建議文字的做法一樣），防止有人改了臨床文字卻沒經過你確認。

## 順序

1. 先寫測試，跑一次確認會失敗。
2. 改 `scoring.py`、`views.py`、兩個模板、CSS，再跑全部 Django 測試、前端測試、e2e。
3. 勾驗收 1–6b，請你做第 7 條。
