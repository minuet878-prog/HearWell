# #105：問卷定義骨架與目錄

日期：2026-10-20。規格：[#105](https://github.com/minuet878-prog/HearWell/issues/105)（母規格 [#99](https://github.com/minuet878-prog/HearWell/issues/99)，決策見 ADR 0005）。基準：`b06ac9b`；功能分支：`refactor/questionnaire-definitions`。

狀態：自動驗證完成，等本人人工驗收。沒有動真實資料，也沒有 migration。

## 行為

- 每份正式問卷（HHIE-S、IOI-HA、HHIA-S、SSQ12-TW）各有一個問卷定義：卡片主題、適用對象、預估分鐘、圖示、排序、作答頁說明段落。文字一個字都沒改，只換了位置。
- 問卷目錄的卡片、作答頁開頭（題數、分鐘、說明段落），以及問卷 API，都改從定義讀。
- 沒有定義的問卷：不出現在目錄、推薦和 API 列表；作答頁的 GET、POST 和 API 詳情都回 404。正式環境沒有這種問卷（本人 2026-10-20 確認）。
- `CODING_STANDARDS.md` 第 9 條改成「說明文字只從 `scoring.py` 或問卷定義產生」，避免跟 ADR 0005 衝突。
- 原本的 `subtitle` 在 `main` 上就沒有任何地方讀取，這次搬家時直接拿掉，沒有帶進定義。

## 驗收對照

勾選代表自動驗證通過，不代替本人實際操作確認。

| 條件 | 自動驗證 | 證據 |
|---|---|---|
| 1. 四份問卷畫面不變 | ✅ 卡片的圖示、適用對象、分鐘數、排序；作答頁的題數、分鐘數、說明段落 | `test_questionnaire_definitions.py:145`、`:152-154`、`:161-163`；既有 `test_questionnaire_cards.py`、`test_pages.py`、`test_recommendations.py` 回歸 |
| 2. 目錄、推薦、API 不列出沒有定義的問卷 | ✅ | `test_questionnaire_definitions.py:64-66`、`:82` |
| 3. 沒有定義的問卷作答網址回 404 | ✅ GET 和 POST 都是 | `test_questionnaire_definitions.py:70`、`:78` |
| 4. 臨時登記的假問卷照定義的文案出現 | ✅ | `test_questionnaire_definitions.py:37-40`；登記用 `patch.dict`，離開時自動還原 |
| 5. 目錄相關的模板與頁面處理不寫死問卷代碼 | ✅ 人工比對 `questionnaire.html`、`questionnaire_icon.html`、`screening.html`、`questionnaire_list` | 自動檢查屬於 #104 |

## 跟著改的既有測試

這些測試原本在驗證「沒有定義的問卷」該怎麼顯示，屬於 #99 拷問 Q8 決定刻意改的行為（#99 的測試例外清單漏列了這一項）：

- `test_questionnaire_cards.py`：假問卷 `fake-later`、`fake-last` 改成先登記定義。原本「沒有適用對象、沒有分鐘數」的斷言，改成核對定義提供的分鐘數。
- `test_pages.py` `test_question_count_is_not_hard_coded`：同上，保留「題數不寫死」的斷言。
- `test_answering.py` 重複答案、`test_api.py` 問卷列表、`test_history.py` 沒有門檻的色帶：改成先登記假定義，驗證的行為沒變。

## 延後的項目

- 結果頁對沒有定義的問卷回 404：延到 #101（已在 issue 留言）。
- API 作答拒絕沒有定義的問卷：延到 #100（已在 issue 留言）。

## 測試與審查

- TDD：先看到目錄測試因為缺少定義套件而失敗、API 測試因為仍列出沒有定義的問卷而失敗，再實作。
- 第一次跑完整 Django 測試，失敗的正好是事先預估的 8 個（都是上面「跟著改的既有測試」）。另外 API 的查詢條件在程式載入時就固定了，測試裡臨時登記的定義看不到，所以改成每次請求時才組查詢。OpenAPI schema 跟改動前逐字相同。
- 最終完整 Django：618 項通過（31.445 秒）。端對端：26 項通過（36.573 秒）。前端：12 檔、182 項通過。`ruff check .` 通過。
- 試驗：刪掉 SSQ12 說明段落的一句，新測試會失敗；試驗後已還原。
- 自審（Matt `/code-review`）：Standards 7 項都是判斷題，修了 3 項（拿掉 `subtitle`、SSQ12 代碼直接從定義匯入、改正 `register` 的說明）。Spec 6 項：補了四份問卷畫面的測試，結果頁與 API 作答延後，其餘不修。
- 交叉審查：本人 2026-10-20 決定這個 session 跳過，只做自審。
- 瀏覽器：沒有用預覽伺服器自己操作，因為要登入本機資料庫的帳號。畫面靠 test client 與端對端測試驗證。

## 人工驗收（請本人操作）

用本機開發伺服器和既有的測試帳號：

1. 開「請選擇問卷」：四張卡片的標題、適用對象、題數、分鐘數、圖示和排序，跟 `main` 一樣。
2. 依序打開四份問卷的作答頁：開頭的題數、分鐘數和說明段落，跟 `main` 一樣（IOI-HA 的常模依據那一段也在）。
3. 隨便挑一份問卷作答到底，確認能正常存檔並看到結果。
