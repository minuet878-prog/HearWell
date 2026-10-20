# #101：結果與計分改從問卷定義讀

日期：2026-10-20。規格：[#101](https://github.com/minuet878-prog/HearWell/issues/101)（母規格 [#99](https://github.com/minuet878-prog/HearWell/issues/99)，決策見 ADR 0005）。基準：`refactor/questionnaire-definitions`（#105，[PR #106](https://github.com/minuet878-prog/HearWell/pull/106) 尚未合併）；功能分支：`refactor/questionnaire-results`。

狀態：自動驗證完成，等本人人工驗收。沒有動真實資料，也沒有 migration。

## 行為

- 問卷定義多了「結果類型」：分級（HHIE-S、HHIA-S）、平均（SSQ12-TW）、常模（IOI-HA）。分級類型另外帶門檻和建議文字；HHIE-S 多一個「要畫趨勢圖」的標記。
- 門檻、HHIE-S 和 HHIA-S 的建議文字、HHIA-S 的共通說明，從 `scoring.py` 原樣搬進各自的定義，數字和文字都沒改，不觸發「先做規則版本號」。「無法判讀」的建議文字是共用的，留在 `scoring.py`。
- 結果頁、我的紀錄、資料匯出、聽力報告、API（分級色帶、紀錄的分數、分級與建議）都改看結果類型，不再判斷問卷代碼。`classify`、`max_score`、`get_advice` 的呼叫方式不變，內部改從定義讀。
- 沒有定義的問卷的紀錄（本人 2026-10-20 決定）：結果頁回 404；API 紀錄、我的紀錄、聽力報告、資料匯出都不列出。正式環境沒有這種紀錄。
- `CODING_STANDARDS.md` 第 11 條把 `scoring.THRESHOLDS` 改成「問卷定義的門檻」。`AGENTS.md`「已知陷阱」裡也有同一個舊名稱，延到 #103 改寫已知陷阱時一起處理（那個檔目前有本人還沒 commit 的修改）。
- 結果頁的模板由結果類型決定，不由每份問卷各自指定：HHIE-S、HHIA-S 本來就共用 `result.html`，SSQ12 用 `ssq12_result.html`，IOI-HA 用自己的頁面。

## 驗收對照

勾選代表自動驗證通過，不代替本人實際操作確認。

| 條件 | 自動驗證 | 證據 |
|---|---|---|
| 1. HHIE-S、HHIA-S 的結果頁、我的紀錄、趨勢圖不變 | ✅ | 建議 `test_pages.py:97`；分級與總分 `:612`；顏色 `:667-672`；HHIA-S `test_hhia_s.py:100-106`；我的紀錄 `test_scoring.py:204`、`test_hhia_s.py:165`；趨勢圖 `test_history.py:35-43,55` |
| 2. SSQ12 的平均或未計算原因不變 | ✅ | 結果頁 `test_ssq12.py:51`；我的紀錄的完整平均（新補）`:55`；未計算原因 `:70`、`:76`、`:175` |
| 3. IOI-HA 的逐題解讀、常模、圖表不變 | ✅ | `test_ioi_ha.py:234-236`；報告 `test_report.py:160,184,334` |
| 4. 匯出欄位不變 | ✅ | `test_export.py:119-122,293-295`；`test_hhia_s.py:265`；SSQ12 的空值 `test_ssq12.py:80-84`、數值平均（新補）`:57` |
| 5. API 分級色帶不變 | ✅ | HHIE-S `test_history.py:35-43`；HHIA-S（新補）`test_hhia_s.py:34`；假定義 `test_questionnaire_definitions.py:211` |
| 6. 計分、結果、匯出的程式與模板不寫死問卷代碼 | ✅ 人工比對 | 剩下的寫死代碼都屬於 #100、#102、#103；自動檢查屬於 #104 |
| （#105 延後項）結果頁對沒有定義的問卷回 404 | ✅ | `test_questionnaire_definitions.py:237`；其他頁不列出 `:240-247` |
| 由定義決定結果 | ✅ 假的分級定義（自己的門檻、建議）驅動結果頁和 API | `test_questionnaire_definitions.py:205-220` |

## 跟著改的既有測試

這些測試都用了沒有定義的假問卷代碼。依本人的決定，改成先登記假定義（預設是「分級但沒有門檻」，結果會是「無法判讀」），保留它們原本要驗證的行為：

- `test_pages.py` 的結果色帶、沒有門檻時不顯示滿分；`test_scoring.py` 的無法判讀結果頁、我的紀錄、分項說明；`test_api.py` 的無法判讀紀錄。
- `test_consent.py` 的同意後回到原頁、`test_ssq12_comparisons.py` 的不同版本（登記成平均類型）、`e2e.main_flow` 的多分頁換行。
- `test_report_parts.py`：`HHIA_S_EXPLANATION` 改從 `screening.questionnaires.hhia_s` 匯入。
- `test_answering.py`、`test_questionnaire_cards.py`：#105 加的登記寫法改成 `enterContext`，行為不變。

## 測試與審查

- TDD：先看到假的分級定義因為缺少「結果類型」而失敗、沒有定義的問卷的結果頁和 API 紀錄仍然看得到，再實作。
- 第一次跑完整測試時，失敗的 10 個全是上面列的假問卷測試；自審後，端對端有 1 個失敗（多分頁換行），原因相同，已修正。
- 最終完整 Django：624 項通過（31.952 秒）。端對端：26 項通過（37.533 秒）。前端沒有改動。`ruff check .` 通過。OpenAPI schema 跟改動前逐字相同。
- 自審（Matt `/code-review`）：Standards 5 項（1 項硬性違規，就是沒有定義的紀錄讓三頁變成 500 錯誤，依本人決定改成不列出；模板裡的 `"average"` 字串改用 `averaged` 屬性；其餘不修）。Spec 4 項（同一個 500 錯誤；補了 3 個斷言；「模板由類型決定」寫在上方「行為」說明；自動檢查由 #104 負責）。門檻與建議文字經審查代理逐字比對，跟搬家前一致。
- 交叉審查：本人 2026-10-20 決定這個 session 跳過。

## 人工驗收（請本人操作）

用本機開發伺服器和既有的測試帳號：

1. 打開一筆 HHIE-S、一筆 HHIA-S 的結果頁：總分、滿分、分級文字與顏色、行動建議跟 `main` 一樣。
2. 打開一筆 SSQ12 的結果頁，再到「我的紀錄」切到 SSQ12 分頁：整體平均或「未計算」的原因不變。
3. 打開一筆 IOI-HA 的結果頁和聽力報告：逐題解讀、常模比較不變。
4. 「我的紀錄」的 HHIE-S 分頁仍然有趨勢圖，其他分頁沒有。
5. 下載「我的資料」：總分、分項、分級、平均欄位跟以前一樣。
