# #100：作答規則改從問卷定義讀

日期：2026-10-20。規格：[#100](https://github.com/minuet878-prog/HearWell/issues/100)（母規格 [#99](https://github.com/minuet878-prog/HearWell/issues/99)，決策見 ADR 0005）。基準：`ec28545`（#109 合併後的 `main`）；功能分支：`refactor/questionnaire-answering`，在 worktree `.claude/worktrees/q100` 實作，沒有切換主資料夾。

狀態：自動驗證完成，等本人人工驗收。沒有動真實資料；有一個 migration，但它不動資料表和資料（`sqlmigrate` 顯示 no-op）。

## 行為

- 每份問卷的定義多了 `choices(題號)`：回傳那一題的選項（值, 文字）。值 `"na"` 代表明確的「不適用」，存成空分數。SSQ12 另外多了 `scale(題號)`，回傳兩端標籤。
- 選項原樣搬家：HHIE-S「常常／有時／從未」（原本綁在答案欄位的 `Score`）、HHIA-S「會／有時／不會」、IOI-HA 每題的選項（原本在 `scoring.py`）、SSQ12 的 0–10 加「不適用」與兩端標籤（原本在 `ssq12.py`，該檔已刪除）。
- 作答頁、網頁表單驗證、寫入 API、答案顯示文字、匯出的選項文字、API 題目的選項與標籤，都改從定義讀。能不能選「不適用」，看那一題的選項有沒有「不適用」。
- 答案欄位拿掉 HHIE-S 選項的綁定（migration 0025）。admin 的作答明細因此改顯示數字（刻意的行為改變）。
- API 作答遇到沒有定義的問卷會拒絕（400），跟網頁作答頁的 404 一致（#105 延後項）。
- React 作答頁讀回草稿時，改看題目選項有沒有「不適用」，不再比對問卷代碼。

## 驗收對照

勾選代表自動驗證通過，不代替本人實際操作確認。

| 條件 | 自動驗證 | 證據 |
|---|---|---|
| 1. 四份問卷的選項與答案文字不變 | ✅ | 網頁作答頁：SSQ12 四組兩端標籤與 HHIE-S 選項 `test_questionnaire_definitions.py:396`、HHIA-S `test_hhia_s.py:140-141`、IOI-HA `test_ioi_ha.py:98,113`；結果逐題 `test_pages.py:647`、`test_hhia_s.py:138`；匯出 `test_export.py:128,284`、`test_ssq12.py:83`；API `test_api.py:286-289,350-354`、`test_hhia_s.py:122-136`、`test_ssq12.py:72,90-98`。審查代理逐字比對搬家前後的選項，完全一致 |
| 2. SSQ12 以外送「不適用」被拒絕，SSQ12 照舊接受 | ✅ | 拒絕（網頁和 API）`test_questionnaire_definitions.py:412`；SSQ12 接受 `test_ssq12.py:64-72,158-170`；嚴格整數 `test_ssq12.py:108-112`；由定義驅動 `test_questionnaire_definitions.py:315,336` |
| 3. migration 只拿掉選項綁定 | ✅ | `0025_answer_score_without_choices.py` 只有一個 `AlterField`，`sqlmigrate` 為 no-op；沒有遺漏 migration `test_standards.py:58` |
| 4. admin 作答明細顯示數字 | ✅ | `test_data_integrity.py:113` |
| 5. React 草稿：有「不適用」選項就保留，沒有就捨棄 | ✅ | 保留 `AnswerApp.test.jsx:532`；捨棄 `AnswerApp.test.jsx:310`（試驗：把判斷改成永遠允許，這個測試會失敗；已還原） |
| 6. 作答相關程式不寫死問卷代碼 | ✅ 人工比對 | 表單、資料模型、API、作答模板、React 作答頁已沒有寫死的代碼；剩下的 `SSQ12`、`IOI_HA` 常數只用在專屬功能（目錄的目的按鈕、HHI 結果頁推薦 SSQ12、IOI-HA 沒有 API）。自動檢查屬於 #104 |
| （#105 延後項）API 拒絕沒有定義的問卷 | ✅ | `test_questionnaire_definitions.py:359` |

## 跟著改的既有測試

- `test_api.py` 的「沒有題目就 400」：照 #100 的留言，先登記假定義 `empty`。
- `test_report.py`、`test_export.py`、`test_ioi_ha.py`：IOI-HA 選項改從 `screening.questionnaires.ioi_ha.ITEM_CHOICES` 匯入（只改名稱）。

## 測試與審查

- TDD：先看到假定義因為缺少 `choices` 而失敗、API 仍接受沒有定義的問卷、前端草稿因為代碼不是 `ssq12-tw` 而被丟掉，再實作。
- 最終：Django 639 項、端對端 26 項、前端 184 項全部通過；`ruff check .` 通過。測試都用獨立的測試資料庫（主資料夾同時有別的工作）。
- 自審（Matt `/code-review`）：Standards 0 項硬性違規（錯誤訊息「0–10」仍是 SSQ12 的寫法、`"na"` 字串分散、匯出查文字的邏輯重複，都不修並說明原因；一處跟票無關的格式改動已還原）。Spec 2 項要修（「拒絕不適用」與「捨棄草稿」沒有測試）都已補上，另補網頁作答頁的選項與兩端標籤斷言。
- 交叉審查：本人 2026-10-20 決定這個 session 跳過。

## 人工驗收（請本人操作）

用本機開發伺服器和既有的測試帳號：

1. 打開 HHIE-S、HHIA-S、IOI-HA、SSQ12 的作答頁：選項文字跟以前一樣；SSQ12 第 9、11、12 題的兩端標籤正確。
2. 各作答一次並看結果頁：逐題答案文字正確；SSQ12 選「不適用」的題目顯示「不適用」。
3. SSQ12 答到一半選了「不適用」，離開再回來：能「接著答」，「不適用」還在。
4. admin 打開一筆作答明細：分數顯示數字。
