# 0036 結果類型由每筆紀錄的結果物件回答

日期：2026-10-26（本人審定，#385 架構審查候選 1；延伸 [ADR 0005](0005-questionnaires-defined-in-code.md)）

## 情境

ADR 0005 把「這份問卷怎麼算」收進定義檔，但「這筆結果屬於哪一種、該怎麼顯示」還是每個用到的地方自己判斷：頁面程式、資料模型、API、模板、匯出都各寫一次 `if result == LEVEL`。同一件事已經有不同說法（THI 的分項在 API 是 0、匯出是 null），加一種新的結果類型要改 8 個以上檔案。

## 決定

- 四種結果類型（分級、平均、常模比對、分量表）各一個 class，放在 `screening/questionnaires/results.py`；問卷定義的 `result` 直接放 class。
- 每筆紀錄的 `submission.result` 是綁定這筆紀錄的結果物件，回答總分、分項、分級、平均、紀錄摘要片段、結果頁模板與資料、匯出欄位。沒有的項目是 None，不是 0。
- 呼叫端（頁面、模板、API、匯出）只問結果物件，不再自己依結果類型分支。

## 理由

考慮過另外兩種形狀：

- **不綁紀錄的策略物件**（像配戴比較的 `TotalComparison`，每個方法都要傳紀錄進去）：模板不能帶參數呼叫方法，模板裡還是得靠 view 先算好、或再寫 if。
- **保留字串，集中成一組函式**（例如 `export_fields(submission)` 裡面分支）：分支只是搬家，新增一種類型還是要改每一個函式。

綁紀錄的物件讓模板直接寫 `submission.result.total`，新增一種類型只要新增一個 class 和它的測試。

## 代價

- `Definition.result` 從字串變成 class；模板會自動呼叫 class，所以要設 `do_not_call_in_templates`。
- Submission 上的舊屬性（`classified`、`ssq_average`、`satisfaction` 等）要全部改名成從結果物件拿，分好幾張票做完（#387–#391），中間有一段時間新舊兩種拿法並存。
